/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Diagnostic synchronous ownership: return only after ALL send completions.
 * This deliberately does not introduce asynchronous DMA-block retention yet.
 */
#include "e200-zerocopy.h"
#include "tcp-transport.h"
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>

struct e200_zc {
    struct tcp_transport *transport;
    pthread_mutex_t lock;
    int fd;
};

struct e200_zc *e200_zc_open(int fd)
{
    struct e200_zc *zc = calloc(1, sizeof(*zc));
    if (!zc)
        return NULL;
    zc->fd = fd;
    zc->transport = tcp_transport_create(fd, "dma-zerocopy", 16 * 1024 * 1024, 1);
    if (!zc->transport) {
        free(zc);
        return NULL;
    }
    pthread_mutex_init(&zc->lock, NULL);
    return zc;
}

ssize_t e200_zc_write(struct e200_zc *zc, const void *data, size_t bytes)
{
    int ret;
    pthread_mutex_lock(&zc->lock);
    ret = tcp_transport_send(zc->transport, data, bytes);
    if (ret)
        shutdown(zc->fd, SHUT_RDWR);
    pthread_mutex_unlock(&zc->lock);
    return ret ? ret : (ssize_t)bytes;
}

int e200_zc_reap(struct e200_zc *zc)
{
    int ret;
    pthread_mutex_lock(&zc->lock);
    ret = tcp_transport_reap(zc->transport);
    pthread_mutex_unlock(&zc->lock);
    return ret;
}

void e200_zc_close(struct e200_zc *zc)
{
    const struct tcp_stats *stats;
    if (!zc)
        return;
    stats = tcp_transport_stats(zc->transport);
    fprintf(stderr, "E200 sync-zc bytes=%llu calls=%llu completed=%llu copied=%llu pending=%llu wait_seconds=%.6f\n",
            (unsigned long long)stats->bytes, (unsigned long long)stats->calls,
            (unsigned long long)stats->completed,
            (unsigned long long)stats->copied_completions,
            (unsigned long long)stats->pending, stats->wait_seconds);
    tcp_transport_destroy(zc->transport);
    pthread_mutex_destroy(&zc->lock);
    free(zc);
}
