/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Legacy framing using upstream block/task APIs, with optional retained TCP
 * ownership. The enqueue worker waits for all TCP references before DMA reuse.
 * No parser transport pointer may outlive its owning connection: stop joins
 * the workers before upstream removes that client. */
#include "e200-legacy-prefetch.h"
#include "e200-affinity.h"
#include "e200-zerocopy.h"
#include <iio/iio-lock.h>
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

struct legacy_block {
    struct iio_block *block;
    struct iio_task_token *enqueue, *dequeue;
    bool ready, owned;
    int result;
};
struct e200_legacy {
    struct iio_buffer_stream *stream;
    struct iio_task *enqueue, *dequeue;
    struct iio_mutex *lock;
    struct iio_cond *changed;
    struct legacy_block blocks[32];
    unsigned count, registered;
    struct e200_zc *zc;
    unsigned hold, released[32], release_head, release_count;
    bool stopped;
};

static void publish(struct e200_legacy *p, struct legacy_block *b, int result)
{
    iio_mutex_lock(p->lock);
    b->result = result;
    b->ready = true;
    iio_cond_signal(p->changed);
    iio_mutex_unlock(p->lock);
}

static int dequeue_block(void *priv, void *data)
{
    struct e200_legacy *p = priv;
    struct legacy_block *b = data;
    int ret = e200_pin("E200_DMA_CPU");
    if (!ret)
        ret = iio_block_dequeue(b->block, false);
    publish(p, b, ret);
    return 0;
}

static int enqueue_block(void *priv, void *data)
{
    struct e200_legacy *p = priv;
    struct legacy_block *b = data;
    int ret = e200_pin("E200_DMA_CPU");
    if (!ret && p->zc)
        ret = e200_zc_wait(p->zc, iio_block_start(b->block));
    if (!ret)
        ret = iio_block_enqueue(b->block, 0, false);
    if (!ret)
        ret = iio_task_token_enqueue(b->dequeue);
    if (ret)
        publish(p, b, ret);
    return 0;
}

struct e200_legacy *e200_legacy_open(struct iio_buffer_stream *stream,
                                    struct iio_block **blocks, unsigned count)
{
    struct e200_legacy *p;
    unsigned i;
    int ret;
    if (count < 2 || count > 32) {
        errno = EINVAL;
        return NULL;
    }
    p = calloc(1, sizeof(*p));
    if (!p)
        return NULL;
    p->stream = stream;
    p->count = count;
    p->lock = iio_mutex_create();
    ret = iio_err(p->lock);
    if (ret) { p->lock = NULL; goto fail; }
    p->changed = iio_cond_create();
    ret = iio_err(p->changed);
    if (ret) { p->changed = NULL; goto fail; }
    p->enqueue = iio_task_create(enqueue_block, p, "legacy-enqueue");
    ret = iio_err(p->enqueue);
    if (ret) { p->enqueue = NULL; goto fail; }
    p->dequeue = iio_task_create(dequeue_block, p, "legacy-dequeue");
    ret = iio_err(p->dequeue);
    if (ret) { p->dequeue = NULL; goto fail; }
    for (i = 0; i < count; i++) {
        struct legacy_block *b = &p->blocks[i];
        b->block = blocks[i];
        b->enqueue = iio_task_token_create(p->enqueue, b);
        ret = iio_err(b->enqueue);
        if (ret) { b->enqueue = NULL; goto fail; }
        b->dequeue = iio_task_token_create(p->dequeue, b);
        ret = iio_err(b->dequeue);
        if (ret) { b->dequeue = NULL; goto fail; }
        /* The existing rw setup already enqueued every physical block. */
        ret = iio_task_token_enqueue(b->dequeue);
        if (ret)
            goto fail;
    }
    iio_task_start(p->enqueue);
    iio_task_start(p->dequeue);
    return p;
fail:
    e200_legacy_close(p);
    errno = -ret;
    return NULL;
}

int e200_legacy_next(struct e200_legacy *p, unsigned index)
{
    struct legacy_block *b;
    int ret = 0;
    if (index >= p->count)
        return -EINVAL;
    b = &p->blocks[index];
    iio_mutex_lock(p->lock);
    while (!b->ready && !p->stopped && !ret)
        ret = iio_cond_wait(p->changed, p->lock, 6000);
    if (!ret)
        ret = p->stopped ? -ECANCELED : b->result;
    if (!ret && b->owned)
        ret = -EBUSY;
    if (!ret) {
        b->ready = false;
        b->owned = true;
    }
    iio_mutex_unlock(p->lock);
    return ret;
}

int e200_legacy_release(struct e200_legacy *p, unsigned index)
{
    struct legacy_block *b;
    int ret;
    if (index >= p->count)
        return -EINVAL;
    b = &p->blocks[index];
    iio_mutex_lock(p->lock);
    if (!b->owned || p->stopped) {
        iio_mutex_unlock(p->lock);
        return -EINVAL;
    }
    b->owned = false;
    iio_mutex_unlock(p->lock);
    /* Ready was published by a running/completed dequeue callback, so these
     * barriers cannot cancel a still-unstarted dequeue needed by the reader. */
    ret = iio_task_cancel_sync(b->dequeue, -1);
    if (!ret)
        ret = iio_task_cancel_sync(b->enqueue, -1);
    if (!ret) {
        /* Hold a bounded number of transmitted blocks before scheduling
         * their completion wait. This leaves the writer free to queue the
         * next payload; it never bypasses the TCP-before-DMA barrier. */
        p->released[(p->release_head + p->release_count) % p->count] = index;
        p->release_count++;
        if (p->release_count > p->hold) {
            b = &p->blocks[p->released[p->release_head]];
            p->release_head = (p->release_head + 1) % p->count;
            p->release_count--;
            ret = iio_task_token_enqueue(b->enqueue);
        }
    }
    if (ret)
        publish(p, b, ret);
    return ret;
}

/* Called under the upstream device thdlist_lock, before exposing the stream
 * to its sole client. The enqueue task has no jobs until the first release. */
int e200_legacy_bind(struct e200_legacy *p, struct e200_zc *zc)
{
    const char *setting = getenv("E200_LEGACY_HOLD");
    unsigned i;
    int ret;
    if (!zc)
        return 0;
    if (!p || p->zc || p->stopped)
        return -EINVAL;
    if (setting) {
        char *end;
        unsigned long hold;
        errno = 0;
        hold = strtoul(setting, &end, 10);
        if (errno || end == setting || *end || hold > p->count - 2)
            return -EINVAL;
        p->hold = hold;
    }
    p->zc = zc;
    for (i = 0; i < p->count; i++) {
        struct iio_block *b = p->blocks[i].block;
        ret = e200_zc_register(zc, iio_block_start(b),
                (char *)iio_block_end(b) - (char *)iio_block_start(b), true);
        if (ret)
            return ret;
        p->registered++;
    }
    return 0;
}

bool e200_legacy_owns(struct e200_legacy *p, struct e200_zc *zc)
{
    return p && zc && p->zc == zc;
}

/* The upstream device thdlist_lock serializes stop/close/bind. A reader may
 * still be in next(), so stop wakes it but does not free the helper. Removing
 * its owning client MUST call this before the parser can destroy its transport.
 * Joining workers precedes unregistering buffers or dropping the borrowed zc.
 */
void e200_legacy_stop(struct e200_legacy *p)
{
    unsigned i;
    if (!p)
        return;
    if (p->lock) {
        iio_mutex_lock(p->lock);
        if (p->stopped) {
            iio_mutex_unlock(p->lock);
            return;
        }
        p->stopped = true;
        if (p->changed)
            iio_cond_signal(p->changed);
        iio_mutex_unlock(p->lock);
    }
    iio_buffer_stream_cancel(p->stream);
    if (p->enqueue)
        iio_task_stop(p->enqueue);
    if (p->dequeue)
        iio_task_stop(p->dequeue);
    for (i = 0; i < p->registered; i++)
        e200_zc_unregister(p->zc, iio_block_start(p->blocks[i].block));
    p->registered = 0;
    p->zc = NULL;
}

void e200_legacy_close(struct e200_legacy *p)
{
    unsigned i;
    if (!p)
        return;
    e200_legacy_stop(p);
    if (p->enqueue)
        iio_task_destroy(p->enqueue);
    if (p->dequeue)
        iio_task_destroy(p->dequeue);
    for (i = 0; i < p->count; i++) {
        if (p->blocks[i].enqueue)
            iio_task_token_destroy(p->blocks[i].enqueue);
        if (p->blocks[i].dequeue)
            iio_task_token_destroy(p->blocks[i].dequeue);
    }
    if (p->changed)
        iio_cond_destroy(p->changed);
    if (p->lock)
        iio_mutex_destroy(p->lock);
    free(p);
}
