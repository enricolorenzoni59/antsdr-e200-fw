/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Experimental, opt-in placement of existing workers; no new queue/thread. */
#ifndef E200_AFFINITY_H
#define E200_AFFINITY_H
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int e200_pin(const char *variable)
{
    static __thread int previous = -1;
    const char *value = getenv(variable);
    cpu_set_t mask;
    int cpu, err;
    if (!value || !*value)
        return 0;
    if (strcmp(value, "0") && strcmp(value, "1"))
        return -EINVAL;
    cpu = value[0] - '0';
    if (previous == cpu)
        return 0;
    CPU_ZERO(&mask);
    CPU_SET(cpu, &mask);
    err = pthread_setaffinity_np(pthread_self(), sizeof(mask), &mask);
    if (err)
        return -err;
    previous = cpu;
    fprintf(stderr, "E200 affinity %s=%d\n", variable, cpu);
    return 0;
}
#endif
