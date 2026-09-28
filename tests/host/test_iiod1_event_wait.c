/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Actual prepared legacy event waiter; deterministic completion-only wakes. */
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/types.h>

struct e200_zc { int error; };
struct parser_pdata { void *pool; struct e200_zc *e200_zc; };
struct ThdEntry { int eventfd; struct parser_pdata *pdata; };
static unsigned polls, reaps, reads;
static bool peer_closed;
static int thread_pool_get_poll_fd(void *pool) { return 3; }
static int poll_nointr(struct pollfd *fds, unsigned count)
{
    assert(count == 3);
    fds[0].revents = polls ? POLLIN : 0;
    fds[1].revents = peer_closed ? POLLRDHUP : (polls ? 0 : POLLERR);
    fds[2].revents = 0;
    polls++;
    return 1;
}
static int e200_zc_reap(struct e200_zc *zc) { reaps++; return zc->error; }
static ssize_t mock_read(int fd, void *data, size_t len)
{
    assert(polls == 2 && reaps == 1 && fd == 1 && len == sizeof(uint64_t));
    *(uint64_t *)data = 1;
    reads++;
    return len;
}
#define read mock_read
#include "actual-event-wait.inc"

int main(void)
{
    pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
    struct e200_zc zc = {0};
    struct parser_pdata pdata = { .e200_zc = &zc };
    struct ThdEntry thd = { .eventfd = 1, .pdata = &pdata };
    assert(!pthread_mutex_lock(&lock));
    assert(!thd_entry_event_wait(&thd, &lock, 2));
    assert(pthread_mutex_trylock(&lock) == EBUSY);
    assert(reaps == 1 && reads == 1);
    polls = reaps = reads = 0;
    zc.error = -ECONNRESET;
    assert(thd_entry_event_wait(&thd, &lock, 2) == -ECONNRESET);
    assert(pthread_mutex_trylock(&lock) == EBUSY && !reads);
    polls = reaps = reads = 0;
    peer_closed = true;
    assert(thd_entry_event_wait(&thd, &lock, 2) == -EPIPE);
    assert(pthread_mutex_trylock(&lock) == EBUSY && !reaps && !reads);
    assert(!pthread_mutex_unlock(&lock));
    assert(!pthread_mutex_destroy(&lock));
    puts("Legacy event wait completion/error/close tests PASS");
    return 0;
}
