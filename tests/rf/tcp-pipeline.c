/* SPDX-License-Identifier: GPL-3.0-or-later */
#define _GNU_SOURCE
#include "tcp-pipeline.h"
#include <errno.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

enum state { FREE, COPYING, READY, IN_FLIGHT };
struct pipeline_slot { void *data; const void *source; size_t size; enum state state; };
struct tcp_pipeline {
    struct tcp_transport *transport;
    struct pipeline_slot *slot;
    struct tcp_stats stats;
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    pthread_t thread;
    unsigned slots, producer;
    size_t size;
    int fd, error;
    bool finished, joined, owned;
    double copy_seconds;
    tcp_pipeline_transform transform;
};

static double clock_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void *sender(void *arg) {
    struct tcp_pipeline *p = arg;
    unsigned consumer = 0;
    double progress = clock_seconds();
    uint64_t last_completed = 0;
    for (;;) {
        int r = tcp_transport_reap(p->transport);
        pthread_mutex_lock(&p->mutex);
        if (r && !p->error) p->error = r;
        p->stats = *tcp_transport_stats(p->transport);
        if (p->stats.completed != last_completed) {
            progress = clock_seconds(); last_completed = p->stats.completed;
        }
        for (unsigned i = 0; i < p->slots; i++) {
            if (p->slot[i].state == IN_FLIGHT && !tcp_transport_slot_pending(p->transport, i)) {
                p->slot[i].state = FREE;
                pthread_cond_broadcast(&p->changed);
            }
        }
        if (p->error) { pthread_mutex_unlock(&p->mutex); break; }
        if (p->slot[consumer].state == READY) {
            struct pipeline_slot *s = &p->slot[consumer];
            s->state = IN_FLIGHT;
            pthread_mutex_unlock(&p->mutex);
            double transformed_seconds = 0;
            ssize_t length = s->size;
            if (p->transform) {
                double begin = clock_seconds();
                length = p->transform(s->data, s->source, s->size);
                transformed_seconds = clock_seconds() - begin;
            }
            r = length < 0 ? (int)length : (size_t)length > p->size ? -EMSGSIZE :
                tcp_transport_send(p->transport, s->data, (size_t)length);
            pthread_mutex_lock(&p->mutex);
            p->copy_seconds += transformed_seconds;
            if (r) p->error = r;
            p->stats = *tcp_transport_stats(p->transport);
            pthread_mutex_unlock(&p->mutex);
            consumer = (consumer + 1) % p->slots;
            progress = clock_seconds();
            continue;
        }
        if (p->finished && !p->stats.pending) { pthread_mutex_unlock(&p->mutex); break; }
        bool pending = p->stats.pending != 0;
        if (pending && clock_seconds() - progress > 10) {
            p->error = -ETIMEDOUT; pthread_mutex_unlock(&p->mutex); break;
        }
        if (!pending) {
            pthread_cond_wait(&p->changed, &p->mutex);
            pthread_mutex_unlock(&p->mutex);
        } else {
            pthread_mutex_unlock(&p->mutex);
            struct pollfd f = {.fd = p->fd, .events = 0};
            poll(&f, 1, 1); /* also recheck newly produced buffers at least every ms */
        }
    }
    int r = tcp_transport_finish(p->transport);
    pthread_mutex_lock(&p->mutex);
    if (r && !p->error) p->error = r;
    p->stats = *tcp_transport_stats(p->transport);
    pthread_cond_broadcast(&p->changed);
    pthread_mutex_unlock(&p->mutex);
    return NULL;
}

static struct tcp_pipeline *create(int fd, size_t size, unsigned slots, unsigned sender_cpu, bool owned, tcp_pipeline_transform transform) {
    if (slots < 2 || slots > 64 || size > 16 * 1024 * 1024 || size * slots > 128 * 1024 * 1024 ||
        sender_cpu > 1) { errno = EINVAL; return NULL; }
    struct tcp_pipeline *p = calloc(1, sizeof(*p));
    if (!p) return NULL;
    p->slots = slots; p->size = size; p->fd = fd; p->owned = owned; p->transform = transform;
    p->slot = calloc(slots, sizeof(*p->slot));
    if (!p->slot) { free(p); return NULL; }
    p->transport = tcp_transport_create(fd, "borrowed-zerocopy", size, slots);
    if (!p->transport) goto fail;
    long page = sysconf(_SC_PAGESIZE);
    if (page < 1) { errno = EINVAL; goto fail; }
    for (unsigned i = 0; owned && i < slots; i++) {
        int r = posix_memalign(&p->slot[i].data, page, size);
        if (r) { errno = r; goto fail; }
        memset(p->slot[i].data, 0, size);
    }
    pthread_mutex_init(&p->mutex, NULL);
    pthread_condattr_t condition;
    pthread_condattr_init(&condition);
    pthread_condattr_setclock(&condition, CLOCK_MONOTONIC);
    pthread_cond_init(&p->changed, &condition);
    pthread_condattr_destroy(&condition);
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    cpu_set_t cpus;
    CPU_ZERO(&cpus); CPU_SET(sender_cpu, &cpus);
    int r = pthread_attr_setaffinity_np(&attr, sizeof(cpus), &cpus);
    if (!r) r = pthread_create(&p->thread, &attr, sender, p);
    pthread_attr_destroy(&attr);
    if (r) {
        pthread_cond_destroy(&p->changed); pthread_mutex_destroy(&p->mutex);
        errno = r; goto fail;
    }
    return p;
fail: {
    int saved = errno;
    for (unsigned i = 0; i < slots; i++) free(p->slot[i].data);
    tcp_transport_destroy(p->transport); free(p->slot); free(p); errno = saved;
    return NULL;
}}

struct tcp_pipeline *tcp_pipeline_create(int fd, size_t size, unsigned slots, unsigned cpu) {
    return create(fd, size, slots, cpu, true, NULL);
}
struct tcp_pipeline *tcp_pipeline_create_borrowed(int fd, size_t size, unsigned slots, unsigned cpu) {
    return create(fd, size, slots, cpu, false, NULL);
}
struct tcp_pipeline *tcp_pipeline_create_transform(int fd, size_t size, unsigned slots, unsigned cpu, tcp_pipeline_transform transform) {
    if (!transform) { errno = EINVAL; return NULL; }
    return create(fd, size, slots, cpu, true, transform);
}
/* One producer only. A successful wait permits that producer to retire the
 * previous DMA buffer attached to this slot, then attach the next block. */
int tcp_pipeline_slot_available(struct tcp_pipeline *p, unsigned slot) {
    if (slot >= p->slots) return 0;
    pthread_mutex_lock(&p->mutex);
    int free_slot = p->slot[slot].state == FREE;
    pthread_mutex_unlock(&p->mutex);
    return free_slot;
}
int tcp_pipeline_wait_available(struct tcp_pipeline *p) {
    pthread_mutex_lock(&p->mutex);
    struct timespec deadline;
    clock_gettime(CLOCK_MONOTONIC, &deadline); deadline.tv_sec += 5;
    while (p->slot[p->producer].state != FREE && !p->error && !p->finished) {
        int r = pthread_cond_timedwait(&p->changed, &p->mutex, &deadline);
        if (r) p->error = -r;
    }
    int r = p->error ? p->error : p->finished ? -EPIPE : 0;
    pthread_mutex_unlock(&p->mutex);
    return r;
}
int tcp_pipeline_send(struct tcp_pipeline *p, const void *data, size_t size) {
    if (size > p->size) return -EMSGSIZE;
    pthread_mutex_lock(&p->mutex);
    struct timespec deadline;
    clock_gettime(CLOCK_MONOTONIC, &deadline); deadline.tv_sec += 5;
    struct pipeline_slot *slot = &p->slot[p->producer];
    while (slot->state != FREE && !p->error) {
        int r = pthread_cond_timedwait(&p->changed, &p->mutex, &deadline);
        if (r) p->error = -r;
    }
    if (p->error || p->finished) {
        int r = p->error ? p->error : -EPIPE;
        pthread_mutex_unlock(&p->mutex); return r;
    }
    slot->state = COPYING;
    pthread_mutex_unlock(&p->mutex);
    double start = clock_seconds();
    if (p->transform) slot->source = data;
    else if (p->owned) tcp_copy_samples(slot->data, data, size);
    else slot->data = (void *)data;
    double elapsed = clock_seconds() - start;
    pthread_mutex_lock(&p->mutex);
    if (p->owned && !p->transform) p->copy_seconds += elapsed;
    slot->size = size; slot->state = READY;
    p->producer = (p->producer + 1) % p->slots;
    pthread_cond_signal(&p->changed);
    pthread_mutex_unlock(&p->mutex);
    return 0;
}

int tcp_pipeline_finish(struct tcp_pipeline *p) {
    pthread_mutex_lock(&p->mutex);
    p->finished = true;
    pthread_cond_signal(&p->changed);
    pthread_mutex_unlock(&p->mutex);
    if (!p->joined) { pthread_join(p->thread, NULL); p->joined = true; }
    return p->error;
}

void tcp_pipeline_stats(struct tcp_pipeline *p, struct tcp_stats *stats) {
    pthread_mutex_lock(&p->mutex);
    *stats = p->stats; stats->copy_seconds += p->copy_seconds;
    pthread_mutex_unlock(&p->mutex);
}

void tcp_pipeline_destroy(struct tcp_pipeline *p) {
    if (!p) return;
    if (!p->joined) tcp_pipeline_finish(p);
    for (unsigned i = 0; i < p->slots; i++)
        if (p->owned && !tcp_transport_slot_pending(p->transport, i)) free(p->slot[i].data);
    tcp_transport_destroy(p->transport); free(p->slot);
    pthread_cond_destroy(&p->changed); pthread_mutex_destroy(&p->mutex); free(p);
}
