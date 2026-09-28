#!/bin/sh
# Standalone ARM server candidate, using the proven rootfs SDK mounted /work.
# The source and output live in /next; no installed baseline files are changed.
set -eu
source=/next/libiio-1.0
aio=${E200_LIBIIO_AIO:-OFF}
case "$aio" in
    OFF) output=/next/libiio1-arm; stage=/next/libiio1-stage ;;
    ON) output=/next/libiio1-aio-arm; stage=/next/libiio1-aio-stage ;;
    *) echo 'E200_LIBIIO_AIO must be ON or OFF' >&2; exit 2 ;;
esac
host=/work/edge-userspace-output/host
[ "$(git -C "$source" rev-parse HEAD)" = 9a929664fd3effa500430626803ac59ecf2f4ed3 ]
export PATH="$host/bin:$PATH"
# Network protocol v1 needs Zstandard even with the USB/AIO backend disabled.
zsource=/next/zstd-1.5.7
zoutput=/next/zstd-arm
[ -s /next/zstd-1.5.7.tar.gz ] || curl -fL --retry 3 \
    https://github.com/facebook/zstd/releases/download/v1.5.7/zstd-1.5.7.tar.gz \
    -o /next/zstd-1.5.7.tar.gz
printf '%s\n' 'eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3  /next/zstd-1.5.7.tar.gz' | sha256sum -c -
[ -d "$zsource" ] || tar -xzf /next/zstd-1.5.7.tar.gz -C /next
cmake -S "$zsource/build/cmake" -B "$zoutput" \
    -DCMAKE_TOOLCHAIN_FILE="$host/share/buildroot/toolchainfile.cmake" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr \
    -DZSTD_BUILD_PROGRAMS=OFF -DZSTD_BUILD_TESTS=OFF -DZSTD_BUILD_STATIC=OFF
cmake --build "$zoutput" -j "${E200_JOBS:-1}"
DESTDIR="$stage" cmake --install "$zoutput"
set --
if [ "$aio" = ON ]; then
    archive=/next/libaio-0.3.113.tar.gz
    [ -s "$archive" ] || curl -fL --retry 3 \
        https://releases.pagure.org/libaio/libaio-0.3.113.tar.gz -o "$archive"
    printf '%s\n' '65c30a102433bf8386581b03fc706d84bd341be249fbdee11a032b237a7b239e8c27413504fef15e2797b1acd67f752526637005889590ecb380e2e120ab0b71  /next/libaio-0.3.113.tar.gz' | sha512sum -c -
    [ -d /next/libaio-0.3.113 ] || tar -xzf "$archive" -C /next
    make -C /next/libaio-0.3.113 -j "${E200_JOBS:-1}" \
        CC="$host/bin/arm-none-linux-gnueabihf-gcc" \
        AR="$host/bin/arm-none-linux-gnueabihf-ar"
    make -C /next/libaio-0.3.113 DESTDIR="$stage" prefix=/usr libdir=/usr/lib install
    set -- "-DLIBAIO_LIBRARIES=$stage/usr/lib/libaio.so" \
        "-DLIBAIO_INCLUDE_DIR=$stage/usr/include"
fi
cmake -S "$source" -B "$output" \
    -DCMAKE_TOOLCHAIN_FILE="$host/share/buildroot/toolchainfile.cmake" \
    "-DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,$stage/usr/lib" \
    -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr \
    -DWITH_LOCAL_BACKEND=ON -DWITH_NETWORK_BACKEND=ON \
    -DWITH_USB_BACKEND=OFF -DWITH_SERIAL_BACKEND=OFF \
    -DWITH_ZSTD=ON "-DLIBZSTD_LIBRARIES=$stage/usr/lib/libzstd.so" \
    "-DLIBZSTD_INCLUDE_DIR=$stage/usr/include" \
    "-DWITH_AIO=$aio" -DWITH_IIOD_USBD=OFF \
    -DWITH_IIOD_SERIAL=OFF -DWITH_IIOD=ON -DWITH_IIOD_V0_COMPAT=ON \
    -DLIBIIO_COMPAT=ON -DWITH_LOCAL_DMABUF_API=ON -DWITH_LOCAL_MMAP_API=ON \
    -DWITH_MODULES=OFF -DWITH_DOC=OFF -DWITH_TESTS=OFF \
    -DPYTHON_BINDINGS=OFF -DCSHARP_BINDINGS=OFF \
    -DHAVE_DNS_SD=OFF "$@"
cmake --build "$output" -j "${E200_JOBS:-1}"
DESTDIR="$stage" cmake --install "$output"
find "$stage" -type f -exec sha256sum '{}' \;
