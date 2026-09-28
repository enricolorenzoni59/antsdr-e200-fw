/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef E200_TCP_TRANSPORT_H
#define E200_TCP_TRANSPORT_H
#include <stddef.h>
#include <stdint.h>

struct tcp_transport;
struct tcp_stats {
    uint64_t bytes, calls, completed, copied_completions, pending;
    double copy_seconds, wait_seconds;
};
/* plain: original send; neon: one NEON staging copy plus ordinary send;
 * zerocopy: NEON staging ring plus MSG_ZEROCOPY;
 * dma-zerocopy: diagnostic direct send, wait before returning ownership to IIO.
 */
struct tcp_transport *tcp_transport_create(int fd, const char *mode, size_t size, unsigned slots);
int tcp_transport_send(struct tcp_transport *t, const void *data, size_t size);
int tcp_transport_finish(struct tcp_transport *t);
const struct tcp_stats *tcp_transport_stats(const struct tcp_transport *t);
/* Call only after closing the socket. Uncompleted storage is deliberately
 * retained until process exit on error, never returned to the malloc pool. */
void tcp_transport_destroy(struct tcp_transport *t);
/* Single-owner primitives for the threaded pipeline. Borrowed buffer storage
 * must not change until this slot has no pending completions. */
int tcp_transport_reap(struct tcp_transport *t);
unsigned tcp_transport_slot_pending(const struct tcp_transport *t, unsigned slot);
void tcp_copy_samples(void *dst, const void *src, size_t size);
#endif
