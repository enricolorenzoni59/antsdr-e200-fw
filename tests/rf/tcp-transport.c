/* SPDX-License-Identifier: GPL-3.0-or-later */
#define _GNU_SOURCE
#include "tcp-transport.h"
#include <errno.h>
#include <time.h>
#include <linux/errqueue.h>
#include <netinet/in.h>
#include <poll.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <unistd.h>
#ifdef __ARM_NEON
#include <arm_neon.h>
#endif

#define MAX_SLOTS 64
#define MAX_PENDING 4096
struct slot { unsigned char *data; unsigned pending; };
struct request { uint32_t id; unsigned slot; bool active; };
struct tcp_transport {
    int fd;
    bool zc, staging, borrowed;
    size_t size;
    unsigned slots, next_slot, ledger_cursor;
    uint32_t next_id;
    struct slot slot[MAX_SLOTS];
    struct request request[MAX_PENDING];
    struct tcp_stats stats;
};

static double monotonic(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void copy_samples(unsigned char *restrict dst, const unsigned char *restrict src, size_t n) {
#ifdef __ARM_NEON
    /* Load a full 128-byte group before storing; normal non-cacheable DMA
     * memory benefits from vector transfers. Unaligned tails remain valid. */
    while (n >= 128) {
        uint8x16_t a = vld1q_u8(src), b = vld1q_u8(src + 16);
        uint8x16_t c = vld1q_u8(src + 32), d = vld1q_u8(src + 48);
        uint8x16_t e = vld1q_u8(src + 64), f = vld1q_u8(src + 80);
        uint8x16_t g = vld1q_u8(src + 96), h = vld1q_u8(src + 112);
        vst1q_u8(dst, a); vst1q_u8(dst + 16, b);
        vst1q_u8(dst + 32, c); vst1q_u8(dst + 48, d);
        vst1q_u8(dst + 64, e); vst1q_u8(dst + 80, f);
        vst1q_u8(dst + 96, g); vst1q_u8(dst + 112, h);
        dst += 128; src += 128; n -= 128;
    }
#endif
    if (n) memcpy(dst, src, n);
}

void tcp_copy_samples(void *dst, const void *src, size_t size) { copy_samples(dst, src, size); }

static void complete_range(struct tcp_transport *t, uint32_t lo, uint32_t hi, bool copied) {
    /* Inclusive wrapping IDs; do not release a slot merely because its LAST
     * send completed. Earlier partial sends may complete out of order. */
    for (unsigned i = 0; i < MAX_PENDING; i++) {
        struct request *r = &t->request[i];
        if (r->active && (uint32_t)(r->id - lo) <= (uint32_t)(hi - lo)) {
            r->active = false;
            t->slot[r->slot].pending--;
            t->stats.pending--;
            t->stats.completed++;
            t->stats.copied_completions += copied;
        }
    }
}

static int drain(struct tcp_transport *t, bool wait) {
    double start = monotonic();
    if (wait) {
        struct pollfd p = {.fd = t->fd, .events = 0};
        int r;
        do { r = poll(&p, 1, 5000); } while (r < 0 && errno == EINTR);
        t->stats.wait_seconds += monotonic() - start;
        if (r <= 0) return -(r == 0 ? ETIMEDOUT : errno);
        if (!(p.revents & POLLERR)) return -EPIPE;
    }
    for (;;) {
        union { struct cmsghdr align; unsigned char bytes[512]; } control;
        char byte;
        struct iovec v = {.iov_base = &byte, .iov_len = 1};
        struct msghdr msg = {.msg_iov = &v, .msg_iovlen = 1,
            .msg_control = control.bytes, .msg_controllen = sizeof(control.bytes)};
        ssize_t n = recvmsg(t->fd, &msg, MSG_ERRQUEUE | MSG_DONTWAIT);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) return errno == EAGAIN ? 0 : -errno;
        if (msg.msg_flags & MSG_CTRUNC) return -EMSGSIZE;
        for (struct cmsghdr *cm = CMSG_FIRSTHDR(&msg); cm; cm = CMSG_NXTHDR(&msg, cm)) {
            if (cm->cmsg_level != SOL_IP || cm->cmsg_type != IP_RECVERR ||
                cm->cmsg_len < CMSG_LEN(sizeof(struct sock_extended_err))) continue;
            const struct sock_extended_err *e = (const void *)CMSG_DATA(cm);
            if (e->ee_errno) return -(int)e->ee_errno;
            if (e->ee_origin == SO_EE_ORIGIN_ZEROCOPY)
                complete_range(t, e->ee_info, e->ee_data, e->ee_code == SO_EE_CODE_ZEROCOPY_COPIED);
        }
    }
}

struct tcp_transport *tcp_transport_create(int fd, const char *mode, size_t size, unsigned slots) {
    if (!size || slots < 1 || slots > MAX_SLOTS || size > 16 * 1024 * 1024 ||
        size * slots > 128 * 1024 * 1024) { errno = EINVAL; return NULL; }
    bool plain = !strcmp(mode, "plain"), neon = !strcmp(mode, "neon");
    bool zc = !strcmp(mode, "zerocopy"), direct = !strcmp(mode, "dma-zerocopy");
    bool borrowed = !strcmp(mode, "borrowed-zerocopy");
    if (!plain && !neon && !zc && !direct && !borrowed) { errno = EINVAL; return NULL; }
    struct tcp_transport *t = calloc(1, sizeof(*t));
    if (!t) return NULL;
    t->fd = fd; t->zc = zc || direct || borrowed; t->staging = neon || zc;
    t->borrowed = borrowed;
    t->size = size; t->slots = (zc || borrowed) ? slots : 1;
    if (t->zc) {
        struct rlimit limit;
        if (getrlimit(RLIMIT_MEMLOCK, &limit)) goto fail;
        rlim_t needed = size * t->slots + 1024 * 1024;
        if (limit.rlim_cur < needed) {
            limit.rlim_cur = needed;
            if (limit.rlim_max < needed) limit.rlim_max = needed;
            if (setrlimit(RLIMIT_MEMLOCK, &limit)) goto fail;
        }
        int one = 1;
        if (setsockopt(fd, SOL_SOCKET, SO_ZEROCOPY, &one, sizeof(one))) goto fail;
    }
    if (t->staging) {
        long page = sysconf(_SC_PAGESIZE);
        if (page < 1) { errno = EINVAL; goto fail; }
        for (unsigned i = 0; i < t->slots; i++) {
            int r = posix_memalign((void **)&t->slot[i].data, page, size);
            if (r) { errno = r; goto fail; }
            memset(t->slot[i].data, 0, size); /* fault pages before acquisition */
        }
    }
    return t;
fail: {
    int saved = errno;
    tcp_transport_destroy(t); errno = saved; return NULL;
}}

int tcp_transport_finish(struct tcp_transport *t) {
    double deadline = monotonic() + 10;
    while (t->stats.pending) {
        int r = drain(t, true);
        if (r) return r;
        if (monotonic() > deadline) return -ETIMEDOUT;
    }
    return 0;
}

int tcp_transport_send(struct tcp_transport *t, const void *data, size_t size) {
    if (size > t->size) return -EMSGSIZE;
    unsigned slot = t->next_slot;
    double deadline = monotonic() + 10;
    if (t->zc) {
        int r = drain(t, false);
        if (r) return r;
        while (t->slot[slot].pending) {
            r = drain(t, true);
            if (r) return r;
            if (monotonic() > deadline) return -ETIMEDOUT;
        }
    }
    if (t->staging) {
        double start = monotonic();
        copy_samples(t->slot[slot].data, data, size);
        t->stats.copy_seconds += monotonic() - start;
        data = t->slot[slot].data;
    }
    size_t offset = 0;
    while (offset < size) {
        if (t->zc && t->stats.pending == MAX_PENDING) {
            int r = drain(t, true);
            if (r) return r;
            if (monotonic() > deadline) return -ETIMEDOUT;
            continue;
        }
        ssize_t n = send(t->fd, (const char *)data + offset, size - offset,
                         MSG_NOSIGNAL | (t->zc ? MSG_ZEROCOPY : 0));
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -(n < 0 ? errno : EIO);
        offset += n; t->stats.bytes += n; t->stats.calls++;
        if (t->zc) {
            while (t->request[t->ledger_cursor].active)
                t->ledger_cursor = (t->ledger_cursor + 1) % MAX_PENDING;
            t->request[t->ledger_cursor] = (struct request){.id = t->next_id++, .slot = slot, .active = true};
            t->slot[slot].pending++; t->stats.pending++;
        }
    }
    t->next_slot = (slot + 1) % t->slots;
    /* Legacy IIO refill releases the previous DMA block. The diagnostic direct
     * path must finish ALL sends before returning to that refill operation. */
    return t->zc && !t->staging && !t->borrowed ? tcp_transport_finish(t) : 0;
}

int tcp_transport_reap(struct tcp_transport *t) { return drain(t, false); }
unsigned tcp_transport_slot_pending(const struct tcp_transport *t, unsigned slot) { return t->slot[slot].pending; }

const struct tcp_stats *tcp_transport_stats(const struct tcp_transport *t) { return &t->stats; }

void tcp_transport_destroy(struct tcp_transport *t) {
    if (!t) return;
    for (unsigned i = 0; i < t->slots; i++)
        if (!t->slot[i].pending) free(t->slot[i].data);
    free(t);
}
