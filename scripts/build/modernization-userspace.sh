#!/bin/sh
# Run in the pinned userspace container. /baseline is the IQ24 work directory;
# /work is a new candidate directory. Never reuse the baseline output directory.
set -eu
stage=${1:?prepare or build}
project=${E200_PROJECT_DIR:-/project}
source=/work/modern-buildroot
external=/work/modern-br2-external
output=/work/edge-userspace-output
toolchain=${E200_USERSPACE_TOOLCHAIN:-14.2}
profile=${E200_USERSPACE_PROFILE:-iq24}
case "$profile" in
    iq24|iq24-bash) ;;
    *) echo 'E200_USERSPACE_PROFILE must be iq24 or iq24-bash' >&2; exit 2 ;;
esac
case "$toolchain" in
    14.2|15.2) ;;
    *) echo 'E200_USERSPACE_TOOLCHAIN must be 14.2 or 15.2' >&2; exit 2 ;;
esac
mkdir -p /work/evidence
if [ "$stage" = prepare ]; then
    [ ! -e "$output/.config" ] || { echo 'Candidate already configured' >&2; exit 1; }
    [ "$(git -C "$source" rev-parse HEAD)" = d5180309b1b66ef3b8eaccca70ad69be8e0729a1 ]
    [ "$(git -C /baseline/modern-buildroot rev-parse HEAD)" = 2e2994de5213abfa63ab5cf5f9291bf62b53d094 ]
    cp -a /baseline/modern-br2-external "$external"
    # Keep the radio stack fixed. The default also preserves the original SDK;
    # the explicit 15.2 experiment uses the pinned Buildroot Arm GNU recipe.
    recipes=package/libiio
    if [ "$toolchain" = 14.2 ]; then
        recipes="$recipes toolchain/toolchain-external/toolchain-external-arm-arm"
    else
        git -C "$source" diff --exit-code HEAD -- \
            toolchain/toolchain-external/toolchain-external-arm-arm
    fi
    for recipe in $recipes; do
        rm -rf "$source/$recipe"
        cp -a "/baseline/modern-buildroot/$recipe" "$source/$recipe"
    done
    printf '%s\n' "$toolchain" > /work/evidence/userspace-toolchain-selection.txt
    printf '%s\n' "$profile" > /work/evidence/userspace-profile-selection.txt
    cp "$project/profiles/iq24/buildroot_defconfig" /work/candidate_defconfig
    if [ "$profile" = iq24-bash ]; then
        cat "$project/profiles/iq24-bash/buildroot.fragment" >> /work/candidate_defconfig
    fi
    make -C "$source" O="$output" BR2_EXTERNAL="$external" \
        E200_BOARD_DIR="$project/board/antsdr-e200" \
        BR2_DEFCONFIG=/work/candidate_defconfig defconfig
    if [ "$profile" = iq24-bash ]; then
        grep -qx BR2_PACKAGE_BASH=y "$output/.config"
        grep -qx BR2_SYSTEM_BIN_SH_BUSYBOX=y "$output/.config"
    fi
    # Download-cache contents are not build outputs; seed a private writable copy.
    cp -a /baseline/modern-buildroot/dl "$source/dl"
    make -C "$source" O="$output" E200_BOARD_DIR="$project/board/antsdr-e200" source
elif [ "$stage" = build ]; then
    selected_profile=$(cat /work/evidence/userspace-profile-selection.txt 2>/dev/null || echo iq24)
    [ "$selected_profile" = "$profile" ] || { echo 'Prepare/build profiles differ' >&2; exit 1; }
    [ "$(cat /work/evidence/userspace-toolchain-selection.txt)" = "$toolchain" ] || {
        echo 'Prepare/build toolchain selections differ' >&2; exit 1;
    }
    if [ "$profile" = iq24-bash ]; then
        grep -qx BR2_PACKAGE_BASH=y "$output/.config"
        grep -qx BR2_SYSTEM_BIN_SH_BUSYBOX=y "$output/.config"
    fi
    make -C "$source" O="$output" E200_BOARD_DIR="$project/board/antsdr-e200" \
        BR2_JLEVEL="${E200_JOBS:-2}" all legal-info
    sh "$project/scripts/build/verify-userspace-in-container.sh"
    if [ "$profile" = iq24-bash ]; then
        qemu-arm -L "$output/target" "$output/target/bin/bash" \
            --noprofile --norc "$project/tests/userspace/bash-smoke.bash" \
            > /work/evidence/bash-smoke.log 2>&1
        [ "$(readlink "$output/target/bin/sh")" = busybox ]
        grep -qx /bin/bash "$output/target/etc/shells"
        grep -Eq '^(\./)?bin/bash$' /work/evidence/cpio-files.txt
        bash_image_check=$(mktemp /work/bash-image-check.XXXXXX)
        trap 'rm -f "$bash_image_check"' 0
        debugfs -R "dump /bin/bash $bash_image_check" "$output/images/rootfs.ext4" \
            > /work/evidence/bash-image-check.log 2>&1
        cmp "$output/target/bin/bash" "$bash_image_check"
        rm "$bash_image_check"
        trap - 0
        printf '%s\n' 'PASS: Bash in CPIO; ext4 executable matches QEMU-tested target.' \
            >> /work/evidence/bash-image-check.log
    fi
    cp "$output/.config" /work/evidence/buildroot.config
    "$output/host/bin/arm-none-linux-gnueabihf-gcc" --version > /work/evidence/compiler.txt
    (cd "$output/images" && sha256sum rootfs.cpio.gz rootfs.cpio.uboot rootfs.ext4) \
        > /work/evidence/artifacts.sha256
else
    echo 'Expected prepare or build' >&2; exit 2
fi
