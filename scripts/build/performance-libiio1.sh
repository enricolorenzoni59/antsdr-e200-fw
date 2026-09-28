#!/bin/sh
# Run in the pinned userspace Docker builder; all outputs are isolated /perf.
# /previous is the completed modernization campaign, /baseline its ARM SDK,
# /project is a read-only export of this repository.
set -eu
source=/perf/libiio1-source
output=/perf/libiio1-build
stage=/perf/libiio1-stage
upstream=/previous/libiio-1.0
host=/baseline/edge-userspace-output/host
pin=9a929664fd3effa500430626803ac59ecf2f4ed3
[ "$(git -C "$upstream" rev-parse HEAD)" = "$pin" ]
zc=${E200_BUILD_ZEROCOPY:-0}
async=${E200_BUILD_ASYNC:-0}
aggregate=${E200_BUILD_AGGREGATE:-0}
socket=${E200_BUILD_SOCKET:-0}
prefetch=${E200_BUILD_PREFETCH:-0}
legacy=${E200_BUILD_LEGACY_PREFETCH:-0}
legacy_async=${E200_BUILD_LEGACY_ASYNC:-0}
dual=${E200_BUILD_DUAL_RX:-0}
for feature in "$zc" "$async" "$aggregate" "$socket" "$prefetch" "$legacy" "$legacy_async" "$dual"; do
    case "$feature" in 0|1) ;; *) echo 'Build switches must be 0 or 1' >&2; exit 2 ;; esac
done
[ "$async" = 0 ] || [ "$zc" = 1 ]
[ "$prefetch" = 0 ] || [ "$async" = 1 ]
[ "$legacy" = 0 ] || [ "$async" = 1 ]
[ "$legacy_async" = 0 ] || [ "$legacy" = 1 ]
[ "$dual" = 0 ] || [ "$legacy_async" = 1 ]
inputs=$(mktemp /perf/.e200-inputs.XXXXXX)
trap 'rm -f "$inputs"' EXIT
{
    printf 'upstream=%s\nfeatures=%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$pin" "$zc" "$async" "$aggregate" "$socket" "$prefetch" "$legacy" "$legacy_async" "$dual"
    sha256sum /project/scripts/build/performance-libiio1.sh \
        /project/profiles/iq24-v1/patches/*.patch /project/profiles/iq24-v1/src/* \
        /project/tests/rf/tcp-transport.c /project/tests/rf/tcp-transport.h \
        /previous/libiio1-stage/usr/lib/libzstd.so
    "$host/bin/arm-none-linux-gnueabihf-gcc" --version
} > "$inputs"
if [ -d "$source" ]; then
    cmp "$inputs" "$source/.e200-prepared-inputs" || {
        echo 'Prepared source has different or unrecorded inputs; use a fresh /perf directory' >&2
        exit 1
    }
fi
if [ ! -d "$source" ]; then
    mkdir -p "$source"
    git -C "$upstream" archive "$pin" | tar -xf - -C "$source"
    patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0001-worker-affinity.patch
    cp /project/profiles/iq24-v1/src/e200-affinity.h "$source/iiod/"
    if [ "${E200_BUILD_ZEROCOPY:-0}" = 1 ]; then
        cp /project/tests/rf/tcp-transport.c /project/tests/rf/tcp-transport.h "$source/iiod/"
        cp /project/profiles/iq24-v1/src/e200-zerocopy.c /project/profiles/iq24-v1/src/e200-zerocopy.h "$source/iiod/"
        patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0002-sync-zerocopy.patch
        if [ "${E200_BUILD_ASYNC:-0}" = 1 ]; then
            cp /project/profiles/iq24-v1/src/e200-zerocopy-async.c "$source/iiod/e200-zerocopy.c"
            cp /project/profiles/iq24-v1/src/e200-zerocopy-async.h "$source/iiod/e200-zerocopy.h"
            patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0003-registered-async-zerocopy.patch
        fi
    fi
    if [ "${E200_BUILD_AGGREGATE:-0}" = 1 ]; then
        patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0004-legacy-request-aggregation.patch
    fi
    if [ "${E200_BUILD_SOCKET:-0}" = 1 ]; then
        patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0005-blocking-socket-experiment.patch
    fi
    if [ "${E200_BUILD_PREFETCH:-0}" = 1 ]; then
        [ "${E200_BUILD_ASYNC:-0}" = 1 ]
        patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0006-native-response-prefetch.patch
    fi
    if [ "${E200_BUILD_LEGACY_PREFETCH:-0}" = 1 ]; then
        [ "${E200_BUILD_ASYNC:-0}" = 1 ]
        cp /project/profiles/iq24-v1/src/e200-legacy-prefetch.c /project/profiles/iq24-v1/src/e200-legacy-prefetch.h "$source/iiod/"
        patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0007-legacy-task-prefetch.patch
    fi
    if [ "${E200_BUILD_LEGACY_ASYNC:-0}" = 1 ]; then
        [ "${E200_BUILD_LEGACY_PREFETCH:-0}" = 1 ]
        cp /project/profiles/iq24-v1/src/e200-legacy-async.c "$source/iiod/e200-legacy-prefetch.c"
        cp /project/profiles/iq24-v1/src/e200-legacy-async.h "$source/iiod/e200-legacy-prefetch.h"
        patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0008-legacy-retained-tcp.patch
        patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0009-legacy-event-completions.patch
    fi
    if [ "$dual" = 1 ]; then
        cp /project/profiles/iq24-v1/src/e200-rx-layout.h "$source/iiod/"
        patch -d "$source" -p1 < /project/profiles/iq24-v1/patches/0010-legacy-dual-rx-layout.patch
    fi
    cp "$inputs" "$source/.e200-prepared-inputs"
fi
cp "$inputs" /perf/build-inputs.txt
mkdir -p "$stage"
cp -a /previous/libiio1-stage/usr "$stage/"
export PATH="$host/bin:$PATH"
cmake -S "$source" -B "$output" \
    -DCMAKE_TOOLCHAIN_FILE="$host/share/buildroot/toolchainfile.cmake" \
    "-DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,$stage/usr/lib" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr \
    -DWITH_LOCAL_BACKEND=ON -DWITH_NETWORK_BACKEND=ON \
    -DWITH_USB_BACKEND=OFF -DWITH_SERIAL_BACKEND=OFF \
    -DWITH_ZSTD=ON "-DLIBZSTD_LIBRARIES=$stage/usr/lib/libzstd.so" \
    "-DLIBZSTD_INCLUDE_DIR=$stage/usr/include" \
    -DWITH_AIO=OFF -DWITH_IIOD_USBD=OFF -DWITH_IIOD_SERIAL=OFF \
    -DWITH_IIOD=ON -DWITH_IIOD_V0_COMPAT=ON -DLIBIIO_COMPAT=ON \
    -DWITH_LOCAL_DMABUF_API=ON -DWITH_LOCAL_MMAP_API=ON \
    -DWITH_MODULES=OFF -DWITH_DOC=OFF -DWITH_TESTS=OFF \
    -DPYTHON_BINDINGS=OFF -DCSHARP_BINDINGS=OFF -DHAVE_DNS_SD=OFF
cmake --build "$output" -j "${E200_JOBS:-2}"
DESTDIR="$stage" cmake --install "$output"
tar -cf /perf/libiio1-candidate.tar -C "$stage" .
sha256sum "$stage/usr/sbin/iiod" "$stage/usr/lib/libiio.so.1.0.0"
