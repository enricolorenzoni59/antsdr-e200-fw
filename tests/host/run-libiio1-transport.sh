#!/bin/sh
# Run in the native Linux test container against the prepared v1 candidate.
set -eu
source=$1
project=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
output=$(mktemp -d)
trap 'rm -rf "$output"' EXIT
sed -e "s@../rf/tcp-transport.c@$source/iiod/tcp-transport.c@" \
    -e "s@../rf/payload-crc.h@$project/tests/rf/payload-crc.h@" \
    "$project/tests/host/test_tcp_transport.c" > "$output/check.c"
cc -std=gnu11 -O1 -g -Wall -Wextra -Werror -Wno-misleading-indentation \
    -fsanitize=address,undefined "$output/check.c" -o "$output/check"
"$output/check"
if grep -q e200_zc_register "$source/iiod/e200-zerocopy.h"; then
    cc -std=gnu11 -O1 -g -Wall -Wextra -Werror -Wno-unused-parameter \
        -fsanitize=address,undefined -I"$source/iiod" \
        "$source/iiod/e200-zerocopy.c" "$project/tests/host/test_iiod1_registered.c" \
        -pthread -o "$output/registry-check"
    "$output/registry-check"
fi
if [ -f "$source/iiod/e200-legacy-prefetch.c" ]; then
    build=$(dirname "$source")/libiio1-build
    cc -std=gnu11 -D_GNU_SOURCE -O1 -g -Wall -Wextra -Werror -Wno-unused-parameter \
        -fsanitize=address,undefined -I"$source/iiod" -I"$source/include" -I"$build" \
        "$source/iiod/e200-legacy-prefetch.c" "$source/task.c" "$source/lock.c" \
        "$project/tests/host/test_iiod1_legacy_prefetch.c" \
        -pthread -o "$output/legacy-check"
    "$output/legacy-check"
    if grep -q E200_LEGACY_ASYNC_HOOKS "$source/iiod/e200-legacy-prefetch.h"; then
        sed -n '/^ssize_t read_line(/,/^void ascii_interpreter/{ /^void ascii_interpreter/d; p; }' \
            "$source/iiod/ops.c" > "$output/actual-read-line.inc"
        cc -std=gnu11 -D_GNU_SOURCE -O1 -g -Wall -Wextra -Werror -Wno-unused-parameter \
            -fsanitize=address,undefined -I"$output" \
            "$project/tests/host/test_iiod1_readline.c" -o "$output/readline-check"
        "$output/readline-check"
        if grep -q E200_LEGACY_HOLD_EXPERIMENT "$source/iiod/e200-legacy-prefetch.h"; then
            sed -n '/^static int thd_entry_event_wait(/,/^\/\* Corresponds to an opened device/{ /^\/\* Corresponds to an opened device/d; p; }' \
                "$source/iiod/ops.c" > "$output/actual-event-wait.inc"
            cc -std=gnu11 -D_GNU_SOURCE -O1 -g -Wall -Wextra -Werror -Wno-unused-parameter \
                -fsanitize=address,undefined -I"$output" \
                "$project/tests/host/test_iiod1_event_wait.c" -pthread -o "$output/event-check"
            "$output/event-check"
        fi
    fi
fi
