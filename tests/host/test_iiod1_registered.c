/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Test the actual registry with a deterministic delayed-completion transport.
 * The real transport ledger has separate range/wrap/partial-send tests. */
#include "e200-zerocopy.h"
#include "tcp-transport.h"
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct tcp_transport {
    unsigned slots, next, pending[64], waits[64];
    struct tcp_stats stats;
    int error;
};
static struct tcp_transport *mock;
struct tcp_transport *tcp_transport_create(int fd, const char *mode, size_t size, unsigned slots)
{
    assert(!strcmp(mode, "borrowed-zerocopy") && size == 1048576 && slots == 64);
    mock = calloc(1, sizeof(*mock));
    assert(mock);
    mock->slots = slots;
    return mock;
}
int tcp_transport_wait_slot(struct tcp_transport *t, unsigned slot)
{
    assert(slot < t->slots);
    if (t->error)
        return t->error;
    if (t->pending[slot]) {
        t->waits[slot]++;
        t->stats.completed += t->pending[slot];
        t->stats.pending -= t->pending[slot];
        t->pending[slot] = 0;
    }
    return 0;
}
int tcp_transport_send(struct tcp_transport *t, const void *data, size_t size)
{
    assert(!t->pending[t->next]);
    t->pending[t->next] = 2; /* one payload, two partial sends */
    t->stats.pending += 2;
    t->stats.calls += 2;
    t->stats.bytes += size;
    t->next = (t->next + 1) % t->slots;
    return 0;
}
int tcp_transport_reap(struct tcp_transport *t) { return t->error; }
const struct tcp_stats *tcp_transport_stats(const struct tcp_transport *t) { return &t->stats; }
void tcp_transport_destroy(struct tcp_transport *t) { free(t); mock = NULL; }

int main(void)
{
    /* Opaque buffer identities: the mock never reads these payload pointers. */
    unsigned char identities[65];
    struct e200_zc *zc;
    unsigned i;
    setenv("E200_ZEROCOPY", "async", 1);
    zc = e200_zc_open(-1);
    assert(zc);
    assert(!e200_zc_eligible(zc, &identities[0], 1048576));
    assert(e200_zc_register(zc, &identities[0], 1048577, true) == -EINVAL);
    for (i = 0; i < 64; i++)
        assert(!e200_zc_register(zc, &identities[i], 1048576, true));
    assert(e200_zc_register(zc, &identities[64], 1048576, true) == -ENOSPC);
    assert(e200_zc_register(zc, &identities[0], 1048576, true) == -EEXIST);
    assert(!e200_zc_eligible(zc, &identities[0], 100));
    assert(!e200_zc_eligible(zc, &identities[0], 1048577));
    assert(e200_zc_write(zc, &identities[0], 1048576) == 1048576);
    assert(e200_zc_write(zc, &identities[1], 1048576) == 1048576);
    assert(mock->stats.pending == 4); /* write returns while pages are retained */
    assert(!e200_zc_wait(zc, &identities[0]));
    assert(mock->pending[0] == 0 && mock->pending[1] == 2);
    assert(!e200_zc_unregister(zc, &identities[1]));
    assert(mock->stats.pending == 0);
    assert(!e200_zc_eligible(zc, &identities[1], 1048576));
    assert(!e200_zc_register(zc, &identities[1], 1048576, true));
    for (i = 0; i < 200; i++) {
        const void *ptr = &identities[i % 64];
        assert(e200_zc_write(zc, ptr, 1048576) == 1048576);
        assert(!e200_zc_wait(zc, ptr));
    }
    assert(mock->stats.pending == 0);
    for (i = 0; i < 64; i++)
        assert(!e200_zc_unregister(zc, &identities[i]));
    /* Legacy payloads must remain synchronous even in async native mode. */
    assert(!e200_zc_register(zc, &identities[0], 1048576, false));
    assert(e200_zc_write(zc, &identities[0], 1048576) == 1048576);
    assert(mock->stats.pending == 0);
    assert(!e200_zc_unregister(zc, &identities[0]));
    /* Failed completion shuts down the connection and prohibits more sends. */
    assert(!e200_zc_register(zc, &identities[0], 1048576, true));
    assert(e200_zc_write(zc, &identities[0], 1048576) == 1048576);
    mock->error = -ECONNRESET;
    assert(e200_zc_wait(zc, &identities[0]) == -ECONNRESET);
    assert(e200_zc_write(zc, &identities[0], 1048576) == -ECONNRESET);
    assert(e200_zc_unregister(zc, &identities[0]) == -ECONNRESET);
    e200_zc_close(zc);
    setenv("E200_ZEROCOPY", "sync", 1);
    zc = e200_zc_open(-1);
    assert(zc && !e200_zc_register(zc, &identities[0], 1048576, true));
    assert(e200_zc_write(zc, &identities[0], 1048576) == 1048576);
    assert(mock->stats.pending == 0);
    assert(!e200_zc_unregister(zc, &identities[0]));
    e200_zc_close(zc);
    puts("Registered payload ownership tests PASS");
    return 0;
}
