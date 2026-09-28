/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef E200_LEGACY_PREFETCH_H
#define E200_LEGACY_PREFETCH_H
#include <iio/iio.h>
#include <stdbool.h>
#define E200_LEGACY_ASYNC_HOOKS 1
#define E200_LEGACY_HOLD_EXPERIMENT 1
struct e200_zc;
struct e200_legacy;
struct e200_legacy *e200_legacy_open(struct iio_buffer_stream *, struct iio_block **, unsigned);
int e200_legacy_next(struct e200_legacy *, unsigned);
int e200_legacy_release(struct e200_legacy *, unsigned);
int e200_legacy_bind(struct e200_legacy *, struct e200_zc *);
bool e200_legacy_owns(struct e200_legacy *, struct e200_zc *);
void e200_legacy_stop(struct e200_legacy *);
void e200_legacy_close(struct e200_legacy *);
#endif
