/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef E200_ZEROCOPY_H
#define E200_ZEROCOPY_H
#include <stddef.h>
#include <sys/types.h>
struct e200_zc;
struct e200_zc *e200_zc_open(int fd);
ssize_t e200_zc_write(struct e200_zc *zc, const void *data, size_t bytes);
int e200_zc_reap(struct e200_zc *zc);
void e200_zc_close(struct e200_zc *zc);
#endif
