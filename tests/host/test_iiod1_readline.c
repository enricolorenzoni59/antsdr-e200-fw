/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Compile the actual prepared ops.c read_line with deterministic poll/recv. */
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/types.h>

struct e200_zc { int error; };
struct parser_pdata {
    bool is_usb, fd_in_is_socket, stop;
    int fd_in;
    void *pool;
    struct e200_zc *e200_zc;
    ssize_t (*readfd)(struct parser_pdata *, void *, size_t);
};
static unsigned polls, reaps, received;
static const char command[] = "READBUF iio:device4 8388608\r\n";
static bool peer_closed;
static int thread_pool_get_poll_fd(void *pool) { return 2; }
static int poll_nointr(struct pollfd *fds, unsigned count)
{
    assert(count == 2);
    /* First wake is a completion, with no incoming command bytes. */
    fds[0].revents = peer_closed ? POLLRDHUP : (polls++ ? POLLIN : POLLERR);
    fds[1].revents = 0;
    return 1;
}
static int e200_zc_reap(struct e200_zc *zc) { reaps++; return zc->error; }
static ssize_t mock_recv(int fd, void *data, size_t len, int flags)
{
    assert(polls >= 2); /* Reading after only POLLERR is the regression. */
    if (flags & MSG_PEEK) {
        assert(len >= sizeof(command) - 1);
        memcpy(data, command, sizeof(command) - 1);
        return sizeof(command) - 1;
    }
    assert((flags & MSG_TRUNC) && len == sizeof(command) - 1);
    received++;
    return len;
}
#define recv mock_recv
#include "actual-read-line.inc"

int main(void)
{
    char buf[128];
    struct e200_zc zc = {0};
    struct parser_pdata pdata = { .fd_in_is_socket = true, .fd_in = 1, .e200_zc = &zc };
    ssize_t n = read_line(&pdata, buf, sizeof(buf));
    assert(n == sizeof(command) - 1 && !memcmp(buf, command, n));
    assert(reaps == 1 && received == 1 && !pdata.stop);
    polls = reaps = received = 0;
    zc.error = -ECONNRESET;
    assert(read_line(&pdata, buf, sizeof(buf)) == -ECONNRESET);
    assert(reaps == 1 && !received);
    polls = reaps = received = 0;
    peer_closed = true;
    assert(read_line(&pdata, buf, sizeof(buf)) == 0 && pdata.stop);
    assert(!reaps && !received);
    puts("Legacy readline completion/error/EOF tests PASS");
    return 0;
}
