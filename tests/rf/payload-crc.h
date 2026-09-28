/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef E200_PAYLOAD_CRC_H
#define E200_PAYLOAD_CRC_H
#include <stddef.h>
#include <stdint.h>
/* IEEE CRC-32, compatible with Python zlib.crc32; integrity diagnostics only. */
static inline void payload_crc_init(uint32_t table[256]) {
    for (unsigned i = 0; i < 256; i++) {
        uint32_t c = i;
        for (unsigned j = 0; j < 8; j++) c = (c >> 1) ^ (0xedb88320U & (0U - (c & 1)));
        table[i] = c;
    }
}
static inline uint32_t payload_crc32(uint32_t crc, const uint32_t table[256],
                                     const void *data, size_t size) {
    const unsigned char *p = data;
    crc = ~crc;
    while (size--) crc = table[(crc ^ *p++) & 255] ^ (crc >> 8);
    return ~crc;
}
#endif
