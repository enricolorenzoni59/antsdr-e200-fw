/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef E200_RX_LAYOUT_H
#define E200_RX_LAYOUT_H
#include <string.h>
#include <iio/iio.h>

/* Return frames per 1 MiB DMA block only for complete RX1 or RX1+RX2 I/Q.
 * Reject mixed/partial masks and unexpected formats rather than inferring
 * channel identity from byte stride alone. Payload bytes are never changed. */
static unsigned int e200_rx_block_frames(const struct iio_device *dev,
                                        const struct iio_channels_mask *mask)
{
    static const char *ids[] = {"voltage0", "voltage1", "voltage2", "voltage3"};
    unsigned int i, seen = 0;
    ssize_t stride;
    const char *name = iio_device_get_name(dev);
    if (!name || strcmp(name, "cf-ad9361-lpc"))
        return 0;
    stride = iio_device_get_sample_size(dev, mask);
    if (stride != 4 && stride != 8)
        return 0;
    for (i = 0; i < iio_device_get_channels_count(dev); i++) {
        const struct iio_channel *ch = iio_device_get_channel(dev, i);
        const struct iio_data_format *fmt;
        const char *id;
        long index;
        if (!iio_channel_is_enabled(ch, mask))
            continue;
        index = iio_channel_get_index(ch);
        id = iio_channel_get_id(ch);
        fmt = iio_channel_get_data_format(ch);
        if (iio_channel_is_output(ch) || !iio_channel_is_scan_element(ch) ||
            index < 0 || index >= 4 || !id || strcmp(id, ids[index]) ||
            (seen & (1U << index)) || !fmt || fmt->length != 16 ||
            fmt->repeat != 1 || fmt->shift || !fmt->is_signed || fmt->is_be ||
            fmt->is_float || (fmt->bits != 12 && fmt->bits != 16))
            return 0;
        seen |= 1U << index;
    }
    if ((stride == 4 && seen != 3) || (stride == 8 && seen != 15))
        return 0;
    return 1048576U / (unsigned int)stride;
}
#endif
