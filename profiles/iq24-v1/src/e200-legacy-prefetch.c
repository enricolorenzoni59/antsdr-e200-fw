/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Legacy framing over upstream block/task APIs. The sender releases a block
 * only after its synchronous registered TCP send completes. Separate upstream
 * enqueue/dequeue tasks keep DMA running while the sender services the client.
 */
#include "e200-legacy-prefetch.h"
#include "e200-affinity.h"
#include <iio/iio-lock.h>
#include <errno.h>
#include <stdbool.h>
#include <stdlib.h>

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
    unsigned count;
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
    if (!ret)
        ret = iio_task_token_enqueue(b->enqueue);
    return ret;
}

void e200_legacy_close(struct e200_legacy *p)
{
    unsigned i;
    if (!p)
        return;
    if (p->lock) {
        iio_mutex_lock(p->lock);
        p->stopped = true;
        if (p->changed)
            iio_cond_signal(p->changed);
        iio_mutex_unlock(p->lock);
    }
    iio_buffer_stream_cancel(p->stream);
    if (p->enqueue) {
        iio_task_stop(p->enqueue);
        iio_task_destroy(p->enqueue);
    }
    if (p->dequeue) {
        iio_task_stop(p->dequeue);
        iio_task_destroy(p->dequeue);
    }
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
