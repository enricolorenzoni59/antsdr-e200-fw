/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef E200_TCP_PIPELINE_H
#define E200_TCP_PIPELINE_H
#include "tcp-transport.h"
#include <sys/types.h>
struct tcp_pipeline;
struct tcp_pipeline *tcp_pipeline_create(int fd, size_t size, unsigned slots, unsigned sender_cpu);
struct tcp_pipeline *tcp_pipeline_create_borrowed(int fd, size_t size, unsigned slots, unsigned sender_cpu);
/* Optional worker-side transform. Source is borrowed until slot becomes free.
 * Return output bytes <= capacity or a negative errno; output pages are owned. */
typedef ssize_t (*tcp_pipeline_transform)(void *dst, const void *src, size_t size);
struct tcp_pipeline *tcp_pipeline_create_transform(int fd, size_t capacity, unsigned slots, unsigned sender_cpu, tcp_pipeline_transform transform);
int tcp_pipeline_slot_available(struct tcp_pipeline *p, unsigned slot);
int tcp_pipeline_wait_available(struct tcp_pipeline *p);
int tcp_pipeline_send(struct tcp_pipeline *p, const void *data, size_t size);
int tcp_pipeline_finish(struct tcp_pipeline *p);
void tcp_pipeline_stats(struct tcp_pipeline *p, struct tcp_stats *stats);
/* Finish/join the worker, then close its socket before destroying storage. */
void tcp_pipeline_destroy(struct tcp_pipeline *p);
#endif
