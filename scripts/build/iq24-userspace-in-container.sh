#!/bin/sh
# Isolated IQ24 rootfs; use the pinned userspace Docker image and /work layout.
set -eu
project=${E200_PROJECT_DIR:-/project}
output=/work/edge-userspace-output
source=/work/modern-buildroot
make -C "$source" O="$output" BR2_EXTERNAL=/work/modern-br2-external \
    E200_BOARD_DIR="$project/board/antsdr-e200" \
    BR2_DEFCONFIG="$project/profiles/iq24/buildroot_defconfig" defconfig
case "${1:-build}" in
 prepare)
    make -C "$source" O="$output" E200_BOARD_DIR="$project/board/antsdr-e200" source
    ;;
 build)
    # Force a clean extraction so the profile patch is the only libiio change.
    make -C "$source" O="$output" E200_BOARD_DIR="$project/board/antsdr-e200" libiio-dirclean
    make -C "$source" O="$output" E200_BOARD_DIR="$project/board/antsdr-e200" \
        BR2_JLEVEL="${E200_JOBS:-2}" all
    sh "$project/scripts/build/verify-userspace-in-container.sh"
    ;;
 *) echo "Usage: $0 prepare|build" >&2; exit 2 ;;
esac
