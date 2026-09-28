/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Compile with the pinned libiio 1.0 public headers. Metadata is mocked;
 * production e200_rx_block_frames() is included unchanged. No RF hardware. */
#include <stdio.h>
#include <stdlib.h>
#include "../../profiles/iq24-v1/src/e200-rx-layout.h"

struct iio_channel {
    const char *id;
    long index;
    unsigned int slot;
    bool output, scan, no_format;
    struct iio_data_format format;
};
struct iio_device {
    const char *name;
    struct iio_channel channels[5];
    unsigned int count;
};
struct iio_channels_mask { unsigned int bits; ssize_t stride; };

const char *iio_device_get_name(const struct iio_device *d) { return d->name; }
unsigned int iio_device_get_channels_count(const struct iio_device *d) { return d->count; }
struct iio_channel *iio_device_get_channel(const struct iio_device *d, unsigned int i)
{ return (struct iio_channel *)&d->channels[i]; }
ssize_t iio_device_get_sample_size(const struct iio_device *d, const struct iio_channels_mask *m)
{ (void)d; return m->stride; }
bool iio_channel_is_enabled(const struct iio_channel *c, const struct iio_channels_mask *m)
{ return !!(m->bits & (1U << c->slot)); }
long iio_channel_get_index(const struct iio_channel *c) { return c->index; }
const char *iio_channel_get_id(const struct iio_channel *c) { return c->id; }
bool iio_channel_is_output(const struct iio_channel *c) { return c->output; }
bool iio_channel_is_scan_element(const struct iio_channel *c) { return c->scan; }
const struct iio_data_format *iio_channel_get_data_format(const struct iio_channel *c)
{ return c->no_format ? NULL : &c->format; }

static struct iio_device device(void)
{
    static const char *ids[] = {"voltage0", "voltage1", "voltage2", "voltage3", "timestamp"};
    struct iio_device d = { .name = "cf-ad9361-lpc", .count = 4 };
    for (unsigned int i = 0; i < 5; i++)
        d.channels[i] = (struct iio_channel) {
            .id = ids[i], .index = i, .slot = i, .scan = true,
            .format = { .length = 16, .bits = 12, .repeat = 1, .is_signed = true }
        };
    return d;
}

static unsigned int checks;
static void check(const char *name, struct iio_device d, unsigned int bits,
                  ssize_t stride, unsigned int expected)
{
    struct iio_channels_mask m = { bits, stride };
    unsigned int result = e200_rx_block_frames(&d, &m);
    if (result != expected) {
        fprintf(stderr, "%s: got %u, expected %u\n", name, result, expected);
        exit(1);
    }
    checks++;
}

int main(void)
{
    struct iio_device d;
    check("RX1", device(), 3, 4, 262144);
    check("dual", device(), 15, 8, 131072);
    /* Exhaust partial/mixed masks at both otherwise eligible strides. */
    for (unsigned int mask = 0; mask < 16; mask++) {
        check("four-byte mask", device(), mask, 4, mask == 3 ? 262144 : 0);
        check("eight-byte mask", device(), mask, 8, mask == 15 ? 131072 : 0);
    }
    check("negative stride", device(), 15, -22, 0);
    check("wide stride", device(), 15, 16, 0);
    d = device(); d.count = 2; check("single DT", d, 3, 4, 262144);
    d = device(); d.name = NULL; check("unnamed", d, 15, 8, 0);
    d = device(); d.name = "other"; check("other device", d, 15, 8, 0);
    d = device(); d.count = 5; check("disabled extra", d, 15, 8, 131072);
    check("enabled extra", d, 31, 8, 0);
    d = device();
    for (unsigned int i = 0; i < 4; i++) d.channels[i].format.bits = 16;
    check("16-bit DSP", d, 15, 8, 131072);
    d = device();
    struct iio_channel swap = d.channels[0];
    d.channels[0] = d.channels[3]; d.channels[3] = swap;
    check("enumeration differs from scan order", d, 15, 8, 131072);
    d = device(); d.channels[3].index = 2; d.channels[3].id = "voltage2";
    check("duplicate identity", d, 15, 8, 0);
    /* Apply every malformed attribute to each enabled component. */
    for (unsigned int i = 0; i < 4; i++) {
#define REJECT(label, assignment) do { d = device(); assignment; check(label, d, 15, 8, 0); } while (0)
        REJECT("negative index", d.channels[i].index = -1);
        REJECT("large index", d.channels[i].index = 4);
        REJECT("duplicate index", d.channels[i].index = (i + 1) % 4);
        REJECT("wrong id", d.channels[i].id = "voltage9");
        REJECT("null id", d.channels[i].id = NULL);
        REJECT("output", d.channels[i].output = true);
        REJECT("non-scan", d.channels[i].scan = false);
        REJECT("missing format", d.channels[i].no_format = true);
        REJECT("32-bit storage", d.channels[i].format.length = 32);
        REJECT("repeat", d.channels[i].format.repeat = 2);
        REJECT("shift", d.channels[i].format.shift = 4);
        REJECT("unsigned", d.channels[i].format.is_signed = false);
        REJECT("big endian", d.channels[i].format.is_be = true);
        REJECT("floating", d.channels[i].format.is_float = true);
        REJECT("wrong precision", d.channels[i].format.bits = 14);
#undef REJECT
    }
    printf("PASS: %u layout checks (mock metadata, production helper)\n", checks);
    return 0;
}
