/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Actual upstream tasks/locks plus a deterministic DMA model. */
#include "e200-legacy-prefetch.h"
#include <iio/iio-backend.h>
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct iio_buffer_stream { bool cancelled, stall; };
struct iio_block {
    struct iio_buffer_stream *stream;
    bool enqueued, reader_holds;
    unsigned generation;
    unsigned char payload[64];
};
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;

#ifdef E200_LEGACY_ASYNC_HOOKS
/* Model delayed TCP references independently of the DMA worker. */
struct e200_zc { bool alive, stall; unsigned registered, waits; };
static struct iio_block *registered_blocks[4];
void *iio_block_start(const struct iio_block *b) { return (void *)b->payload; }
void *iio_block_end(const struct iio_block *b) { return (void *)(b->payload + sizeof(b->payload)); }
int e200_zc_register(struct e200_zc *zc, const void *ptr, size_t size, bool retained)
{
    assert(zc->alive && retained && size == 64);
    zc->registered++;
    return 0;
}
int e200_zc_wait(struct e200_zc *zc, const void *ptr)
{
    unsigned i;
    pthread_mutex_lock(&lock);
    assert(zc->alive);
    while (zc->stall)
        pthread_cond_wait(&changed, &lock);
    zc->waits++;
    for (i = 0; i < 4; i++)
        if (registered_blocks[i]->payload == ptr)
            registered_blocks[i]->reader_holds = false;
    pthread_mutex_unlock(&lock);
    return 0;
}
int e200_zc_unregister(struct e200_zc *zc, const void *ptr)
{
    assert(zc->alive && zc->registered);
    e200_zc_wait(zc, ptr);
    zc->registered--;
    return 0;
}
#endif

size_t iio_strlcpy(char *dst, const char *src, size_t size)
{
    size_t n = strlen(src);
    if (size) {
        size_t copy = n < size-1 ? n : size-1;
        memcpy(dst, src, copy);
        dst[copy] = 0;
    }
    return n;
}
int iio_block_enqueue(struct iio_block *b, size_t bytes_used, bool cyclic)
{
    int ret = 0;
    pthread_mutex_lock(&lock);
    assert(!b->reader_holds && !b->enqueued);
    if (b->stream->cancelled)
        ret = -ECANCELED;
    else
        b->enqueued = true;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&lock);
    return ret;
}
int iio_block_dequeue(struct iio_block *b, bool nonblock)
{
    int ret = 0;
    pthread_mutex_lock(&lock);
    while (b->stream->stall && !b->stream->cancelled)
        pthread_cond_wait(&changed, &lock);
    if (b->stream->cancelled)
        ret = -ECANCELED;
    else {
        assert(b->enqueued && !b->reader_holds);
        b->enqueued = false;
        b->generation++;
        memset(b->payload, b->generation & 255, sizeof(b->payload));
    }
    pthread_mutex_unlock(&lock);
    return ret;
}
void iio_buffer_stream_cancel(struct iio_buffer_stream *s)
{
    pthread_mutex_lock(&lock);
    s->cancelled = true;
    pthread_cond_broadcast(&changed);
    pthread_mutex_unlock(&lock);
}

int main(void)
{
    struct iio_buffer_stream stream = {0};
    struct iio_block blocks[4] = {0}, *ptrs[4];
    struct e200_legacy *p;
    unsigned i;
    unsetenv("E200_DMA_CPU"); /* Host container CPU numbers need not include0. */
    for (i = 0; i < 4; i++) {
        blocks[i].stream = &stream;
        blocks[i].enqueued = true;
        ptrs[i] = &blocks[i];
    }
    p = e200_legacy_open(&stream, ptrs, 4);
    assert(p);
    assert(e200_legacy_release(p, 0) == -EINVAL);
    for (i = 0; i < 200; i++) {
        unsigned index = i % 4;
        unsigned char retained[64];
        assert(!e200_legacy_next(p, index));
        pthread_mutex_lock(&lock);
        blocks[index].reader_holds = true;
        memcpy(retained, blocks[index].payload, sizeof(retained));
        pthread_mutex_unlock(&lock);
        usleep(500); /* Other blocks may advance, this one must remain intact. */
        pthread_mutex_lock(&lock);
        assert(!memcmp(retained, blocks[index].payload, sizeof(retained)));
        blocks[index].reader_holds = false;
        pthread_mutex_unlock(&lock);
        assert(!e200_legacy_release(p, index));
    }
    e200_legacy_close(p);
    assert(stream.cancelled);
    /* Cancel while the upstream dequeue worker is blocked in DMA. */
    stream = (struct iio_buffer_stream){ .stall = true };
    for (i = 0; i < 4; i++)
        blocks[i].enqueued = true;
    p = e200_legacy_open(&stream, ptrs, 4);
    assert(p);
    usleep(1000);
    e200_legacy_close(p);
    assert(stream.cancelled);
#ifdef E200_LEGACY_ASYNC_HOOKS
    for (unsigned hold_case = 0; hold_case < 2; hold_case++) {
        struct e200_zc zc = { .alive = true, .stall = true };
        unsigned generation;
#ifdef E200_LEGACY_HOLD_EXPERIMENT
        setenv("E200_LEGACY_HOLD", hold_case ? "2" : "0", 1);
#endif
        stream = (struct iio_buffer_stream){0};
        for (i = 0; i < 4; i++) {
            blocks[i].enqueued = true;
            blocks[i].reader_holds = false;
            registered_blocks[i] = &blocks[i];
        }
        p = e200_legacy_open(&stream, ptrs, 4);
        assert(p && !e200_legacy_bind(p, &zc));
        assert(zc.registered == 4 && e200_legacy_owns(p, &zc));
        assert(e200_legacy_bind(p, &zc) == -EINVAL);
        assert(!e200_legacy_next(p, 0));
        pthread_mutex_lock(&lock);
        blocks[0].reader_holds = true;
        generation = blocks[0].generation;
        pthread_mutex_unlock(&lock);
        assert(!e200_legacy_release(p, 0));
        usleep(1000);
        pthread_mutex_lock(&lock);
        assert(blocks[0].reader_holds && !blocks[0].enqueued);
        assert(blocks[0].generation == generation);
        zc.stall = false;
        pthread_cond_broadcast(&changed);
        pthread_mutex_unlock(&lock);
        for (i = 1; i < 200; i++) {
            unsigned index = i % 4;
            assert(!e200_legacy_next(p, index));
            pthread_mutex_lock(&lock);
            blocks[index].reader_holds = true;
            pthread_mutex_unlock(&lock);
            assert(!e200_legacy_release(p, index));
        }
        /* Model removing the parser while the rw thread still owns helper p. */
        e200_legacy_stop(p);
        assert(!zc.registered && zc.waits && !e200_legacy_owns(p, &zc));
        zc.alive = false;
        assert(e200_legacy_next(p, 0) == -ECANCELED);
        e200_legacy_stop(p);
        e200_legacy_close(p); /* Must not access the destroyed parser transport. */
    }
    unsetenv("E200_LEGACY_HOLD");
#endif
    puts("Legacy upstream-task ownership/cancellation tests PASS");
    return 0;
}
