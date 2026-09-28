#!/bin/sh
# First modernization rung: current ADI kernel, baseline compiler/rootfs/FPGA.
set -eu
root=${E200_BUILD_ROOT:-/work}
source=$root/modern-linux
output=$root/edge-kernel-output
compiler=${E200_CROSS_COMPILE:-$root/vendor/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-}
expected=bf1d49f17fa9e15bc40be2615ef67cdf023f660a
[ "$(git -C "$source" rev-parse HEAD)" = "$expected" ] || {
    echo 'Unexpected kernel revision; refusing build' >&2
    exit 1
}
[ -x "${compiler}gcc" ] || {
    echo 'Build the pinned vendor toolchain or set E200_CROSS_COMPILE' >&2
    exit 1
}
# Preserve the old compiler for this isolated kernel experiment. Kernel 6.12
# supports GCC >=5.1; modern userspace will use the matched ADI toolchain instead.
export KBUILD_BUILD_USER=e200-builder KBUILD_BUILD_HOST=reproducible
export SOURCE_DATE_EPOCH
SOURCE_DATE_EPOCH=$(git -C "$source" show -s --format=%ct HEAD)
export KBUILD_BUILD_TIMESTAMP
KBUILD_BUILD_TIMESTAMP=$(date -u -d "@$SOURCE_DATE_EPOCH" '+%a %b %d %T UTC %Y')
export KBUILD_BUILD_VERSION=1
mkdir -p "$output"
make -C "$source" O="$output" ARCH=arm CROSS_COMPILE="$compiler" zynq_e200_defconfig
make -C "$source" O="$output" ARCH=arm CROSS_COMPILE="$compiler" \
    -j "${E200_JOBS:-8}" zImage uImage LOADADDR=0x8000 xilinx/zynq-e200.dtb xilinx/zynq-e200-dual-rx.dtb
make -C "$source" O="$output" ARCH=arm CROSS_COMPILE="$compiler" savedefconfig
printf '%s\n' 'KERNEL BUILD PASS. Hardware validation is a separate gate.'
