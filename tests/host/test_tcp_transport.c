/* SPDX-License-Identifier: GPL-3.0-or-later
 * Linux-native tests for completion lifetime and arbitrary copy tails.
 */
#include "../rf/tcp-transport.c"
#include "../rf/payload-crc.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    uint32_t table[256]; payload_crc_init(table);
    assert(payload_crc32(0, table, "123456789", 9) == 0xcbf43926);
    uint32_t crc = payload_crc32(0, table, "1234", 4);
    assert(payload_crc32(crc, table, "56789", 5) == 0xcbf43926);
    assert(payload_crc32(crc, table, "", 0) == crc);
    unsigned char src[1024], dst[1024];
    for (unsigned i = 0; i < sizeof(src); i++) src[i] = (i * 37) & 255;
    for (unsigned offset = 0; offset < 16; offset++) {
        for (unsigned n = 0; n < 768; n++) {
            memset(dst, 0xa5, sizeof(dst));
            copy_samples(dst + offset, src + 3, n);
            assert(!memcmp(dst + offset, src + 3, n));
            for (unsigned i = 0; i < offset; i++) assert(dst[i] == 0xa5);
            for (unsigned i = offset + n; i < sizeof(dst); i++) assert(dst[i] == 0xa5);
        }
    }
    struct tcp_transport *t = calloc(1, sizeof(*t));
    assert(t);
    t->slots = 2;
    t->slot[0].pending = 2; t->slot[1].pending = 1;
    t->stats.pending = 3;
    t->request[0] = (struct request){.id = UINT32_MAX, .slot = 0, .active = true};
    t->request[1] = (struct request){.id = 0, .slot = 0, .active = true};
    t->request[2] = (struct request){.id = 1, .slot = 1, .active = true};
    complete_range(t, 0, 0, false); /* last partial send first: cannot release */
    assert(t->slot[0].pending == 1 && t->stats.pending == 2);
    complete_range(t, UINT32_MAX, 0, true); /* wrapping coalesced completion */
    assert(t->slot[0].pending == 0 && t->slot[1].pending == 1);
    assert(t->stats.completed == 2 && t->stats.copied_completions == 1);
    complete_range(t, UINT32_MAX, 0, false); /* duplicate must not underflow */
    assert(t->stats.pending == 1);
    complete_range(t, 1, 1, false);
    assert(t->stats.pending == 0 && t->stats.completed == 3);
    tcp_transport_destroy(t);
    puts("Transport lifetime and copy-boundary tests PASS");
    return 0;
}
