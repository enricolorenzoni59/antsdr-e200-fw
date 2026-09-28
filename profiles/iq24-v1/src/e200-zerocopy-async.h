/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef E200_ZEROCOPY_H
#define E200_ZEROCOPY_H
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
struct e200_zc;
struct e200_zc *e200_zc_open(int fd);
int e200_zc_register(struct e200_zc *, const void *, size_t, bool);
int e200_zc_wait(struct e200_zc *, const void *);
int e200_zc_unregister(struct e200_zc *, const void *);
bool e200_zc_eligible(struct e200_zc *, const void *, size_t);
ssize_t e200_zc_write(struct e200_zc *, const void *, size_t);
int e200_zc_reap(struct e200_zc *);
void e200_zc_close(struct e200_zc *);
#endif
