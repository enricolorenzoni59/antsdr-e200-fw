/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Registered DMA payload only. One ledger owner under lock; re-enqueue/free
 * waits for EVERY partial send referencing the relevant block. */
#include "e200-zerocopy.h"
#include "tcp-transport.h"
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>

#define E200_SLOTS 64
#define E200_BLOCK_BYTES 1048576
struct payload { const void *ptr; size_t size; bool native; };
struct e200_zc {
    struct tcp_transport *transport;
    pthread_mutex_t lock;
    struct payload payload[E200_SLOTS];
    const void *flight[E200_SLOTS];
    unsigned next;
    bool asynchronous;
    int fd, error;
};

static int fail(struct e200_zc *zc, int error)
{
    if (error) {
        zc->error = error;
        shutdown(zc->fd, SHUT_RDWR);
    }
    return error;
}

static int wait_locked(struct e200_zc *zc, const void *ptr)
{
    unsigned i;
    int ret = zc->error;
    if (ret)
        return ret;
    for (i = 0; i < E200_SLOTS; i++) {
        if (zc->flight[i] != ptr)
            continue;
        ret = tcp_transport_wait_slot(zc->transport, i);
        if (ret)
            return fail(zc, ret);
        zc->flight[i] = NULL;
    }
    return 0;
}

struct e200_zc *e200_zc_open(int fd)
{
    struct e200_zc *zc = calloc(1, sizeof(*zc));
    const char *mode = getenv("E200_ZEROCOPY");
    if (!zc)
        return NULL;
    zc->fd = fd;
    zc->asynchronous = mode && !strcmp(mode, "async");
    zc->transport = tcp_transport_create(fd, "borrowed-zerocopy", E200_BLOCK_BYTES, E200_SLOTS);
    if (!zc->transport) {
        free(zc);
        return NULL;
    }
    pthread_mutex_init(&zc->lock, NULL);
    return zc;
}

int e200_zc_register(struct e200_zc *zc, const void *ptr, size_t size, bool native)
{
    unsigned i;
    int ret = -ENOSPC;
    if (!zc)
        return 0;
    if (!ptr || !size || size > E200_BLOCK_BYTES)
        return -EINVAL;
    pthread_mutex_lock(&zc->lock);
    for (i = 0; i < E200_SLOTS; i++) {
        if (zc->payload[i].ptr == ptr) {
            ret = -EEXIST;
            goto out;
        }
    }
    for (i = 0; i < E200_SLOTS; i++) {
        if (!zc->payload[i].ptr) {
            zc->payload[i] = (struct payload){ptr, size, native};
            ret = 0;
            break;
        }
    }
out:
    pthread_mutex_unlock(&zc->lock);
    return ret;
}

bool e200_zc_eligible(struct e200_zc *zc, const void *ptr, size_t size)
{
    unsigned i;
    bool result = false;
    if (!zc || size < 16384)
        return false;
    pthread_mutex_lock(&zc->lock);
    for (i = 0; i < E200_SLOTS; i++)
        if (zc->payload[i].ptr == ptr && size <= zc->payload[i].size)
            result = true;
    pthread_mutex_unlock(&zc->lock);
    return result;
}

ssize_t e200_zc_write(struct e200_zc *zc, const void *ptr, size_t bytes)
{
    unsigned i;
    int ret = -EINVAL;
    bool native = false, found = false;
    pthread_mutex_lock(&zc->lock);
    for (i = 0; i < E200_SLOTS; i++) {
        if (zc->payload[i].ptr == ptr && bytes <= zc->payload[i].size) {
            native = zc->payload[i].native;
            found = true;
            break;
        }
    }
    if (!found)
        goto out;
    ret = zc->error;
    if (ret)
        goto out;
    ret = tcp_transport_wait_slot(zc->transport, zc->next);
    if (ret)
        goto out;
    /* Record before sending, including the partial-send error case. */
    zc->flight[zc->next] = ptr;
    ret = tcp_transport_send(zc->transport, ptr, bytes);
    if (!ret) {
        zc->next = (zc->next + 1) % E200_SLOTS;
        if (!zc->asynchronous || !native)
            ret = wait_locked(zc, ptr);
    }
out:
    if (ret)
        fail(zc, ret);
    pthread_mutex_unlock(&zc->lock);
    return ret ? ret : (ssize_t)bytes;
}

int e200_zc_wait(struct e200_zc *zc, const void *ptr)
{
    int ret;
    if (!zc)
        return 0;
    pthread_mutex_lock(&zc->lock);
    ret = wait_locked(zc, ptr);
    pthread_mutex_unlock(&zc->lock);
    return ret;
}

int e200_zc_unregister(struct e200_zc *zc, const void *ptr)
{
    unsigned i;
    int ret;
    if (!zc)
        return 0;
    pthread_mutex_lock(&zc->lock);
    ret = wait_locked(zc, ptr);
    for (i = 0; i < E200_SLOTS; i++)
        if (zc->payload[i].ptr == ptr)
            zc->payload[i] = (struct payload){0};
    pthread_mutex_unlock(&zc->lock);
    return ret;
}

int e200_zc_reap(struct e200_zc *zc)
{
    int ret;
    pthread_mutex_lock(&zc->lock);
    ret = zc->error ? zc->error : tcp_transport_reap(zc->transport);
    if (ret)
        fail(zc, ret);
    pthread_mutex_unlock(&zc->lock);
    return ret;
}

void e200_zc_close(struct e200_zc *zc)
{
    const struct tcp_stats *stats;
    if (!zc)
        return;
    stats = tcp_transport_stats(zc->transport);
    fprintf(stderr, "E200 registered-zc async=%d bytes=%llu calls=%llu completed=%llu copied=%llu pending=%llu wait_seconds=%.6f error=%d\n",
            zc->asynchronous, (unsigned long long)stats->bytes,
            (unsigned long long)stats->calls, (unsigned long long)stats->completed,
            (unsigned long long)stats->copied_completions,
            (unsigned long long)stats->pending, stats->wait_seconds, zc->error);
    tcp_transport_destroy(zc->transport);
    pthread_mutex_destroy(&zc->lock);
    free(zc);
}
