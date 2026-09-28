/* SPDX-License-Identifier: GPL-3.0-or-later
 * Linux loopback integration: backpressure, ring reuse, owned/borrowed lifetime.
 * Loopback may copy; real-board evidence separately checks copied == 0.
 */
#define _GNU_SOURCE
#include "../rf/tcp-pipeline.h"
#include <arpa/inet.h>
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
enum { SIZE = 32768, SLOTS = 4, BLOCKS = 64 };
struct receiver { int fd; size_t bytes, block_size; unsigned char xor_mask; int error; };
static void *receive(void *arg) {
    struct receiver *r = arg;
    unsigned char data[8192];
    for (;;) {
        ssize_t n = recv(r->fd, data, sizeof(data), 0);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { r->error = errno; break; }
        if (!n) break;
        for (ssize_t i = 0; i < n; i++) {
            if (data[i] != (unsigned char)(((r->bytes + i) / r->block_size) ^ r->xor_mask)) {
                r->error = EILSEQ; return NULL;
            }
        }
        r->bytes += n;
        usleep(1000);
    }
    return NULL;
}
static ssize_t transform_half(void *dst, const void *src, size_t size) {
    unsigned char *out = dst; const unsigned char *in = src;
    for (size_t i = 0; i < size / 2; i++) out[i] = in[i] ^ 0x5a;
    return size / 2;
}
static ssize_t transform_fail(void *dst, const void *src, size_t size) {
    if (*(const unsigned char *)src == 5) return -ERANGE;
    return transform_half(dst, src, size);
}
static void run(int borrowed) {
    int listener = socket(AF_INET, SOCK_STREAM, 0);
    assert(listener >= 0);
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    assert(!bind(listener, (void *)&a, sizeof(a)));
    socklen_t alen = sizeof(a);
    assert(!getsockname(listener, (void *)&a, &alen));
    assert(!listen(listener, 1));
    int fd = socket(AF_INET, SOCK_STREAM, 0); assert(fd >= 0);
    assert(!connect(fd, (void *)&a, sizeof(a)));
    struct receiver r = {.fd = accept(listener, NULL, NULL), .block_size = borrowed >= 2 ? SIZE / 2 : SIZE, .xor_mask = borrowed >= 2 ? 0x5a : 0}; assert(r.fd >= 0);
    close(listener);
    struct timeval timeout = {.tv_sec = 5};
    assert(!setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)));
    assert(!setsockopt(r.fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)));
    pthread_t reader; assert(!pthread_create(&reader, NULL, receive, &r));
    cpu_set_t allowed; assert(!sched_getaffinity(0, sizeof(allowed), &allowed));
    unsigned cpu = CPU_ISSET(0, &allowed) ? 0 : 1;
    assert(CPU_ISSET(cpu, &allowed));
    struct tcp_pipeline *p = borrowed >= 2 ? tcp_pipeline_create_transform(fd, SIZE, SLOTS, cpu, borrowed == 3 ? transform_fail : transform_half) : borrowed ? tcp_pipeline_create_borrowed(fd, SIZE, SLOTS, cpu) :
                                       tcp_pipeline_create(fd, SIZE, SLOTS, cpu);
    if (!p) perror("pipeline");
    assert(p);
    unsigned char *source[SLOTS];
    for (unsigned i = 0; i < SLOTS; i++) {
        assert(!posix_memalign((void **)&source[i], 4096, SIZE));
    }
    for (unsigned i = 0; i < BLOCKS; i++) {
        unsigned slot = i % SLOTS;
        int available = tcp_pipeline_wait_available(p);
        if (available && borrowed == 3) { assert(available == -ERANGE); break; }
        assert(!available);
        assert(tcp_pipeline_slot_available(p, slot));
        memset(source[slot], i, SIZE);
        int sent = tcp_pipeline_send(p, source[slot], SIZE);
        if (sent && borrowed == 3) { assert(sent == -ERANGE); break; }
        assert(!sent);
        if (!borrowed) memset(source[slot], 0xff, SIZE);
    }
    assert(tcp_pipeline_finish(p) == (borrowed == 3 ? -ERANGE : 0));
    struct tcp_stats stats; tcp_pipeline_stats(p, &stats);
    size_t expected = r.block_size * (borrowed == 3 ? 5 : BLOCKS);
    assert(stats.bytes == expected && stats.calls > 0);
    assert(stats.completed == stats.calls && stats.pending == 0);
    if (borrowed == 1) assert(stats.copy_seconds == 0);
    assert(!shutdown(fd, SHUT_WR));
    assert(!pthread_join(reader, NULL));
    assert(!r.error && r.bytes == expected);
    close(fd); close(r.fd);
    tcp_pipeline_destroy(p);
    for (unsigned i = 0; i < SLOTS; i++) free(source[i]);
}
int main(void) {
    run(0); run(1); run(2); run(3);
    puts("Owned/borrowed/transformed pipeline integrity, backpressure and transform-error tests PASS");
    return 0;
}
