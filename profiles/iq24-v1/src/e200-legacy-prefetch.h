/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef E200_LEGACY_PREFETCH_H
#define E200_LEGACY_PREFETCH_H
#include <iio/iio.h>
struct e200_legacy;
struct e200_legacy *e200_legacy_open(struct iio_buffer_stream *, struct iio_block **, unsigned);
int e200_legacy_next(struct e200_legacy *, unsigned);
int e200_legacy_release(struct e200_legacy *, unsigned);
void e200_legacy_close(struct e200_legacy *);
#endif
