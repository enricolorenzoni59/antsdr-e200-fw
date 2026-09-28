#!/usr/bin/env bash
# Build files only. Never writes a card, changes boot state or accesses the radio.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
stage=${1:-all}
case "$stage" in all|images|fetch|kernel|userspace|iiod|package|test|sources) ;; *) echo 'Expected all|images|fetch|kernel|userspace|iiod|package|test|sources' >&2; exit 2;; esac
[[ $(uname -s) == Linux && $(uname -m) == x86_64 && $(id -u) != 0 ]] || {
    echo 'Use a non-root user on Linux x86-64 with Docker.' >&2; exit 1;
}
work=${E200_RELEASE_WORK:-$project/work/release}
mkdir -p "$work"
work=$(cd -- "$work" && pwd)
mkdir -p "$work"/{evidence,baseline,bash,next,perf,package,vendor}
docker=(docker)
if [[ ${E200_DOCKER_SUDO:-0} == 1 ]]; then docker=(sudo -n docker); fi
jobs=${E200_JOBS:-2}
step() { [[ $stage == all || $stage == "$1" ]]; }
if step images; then
    "${docker[@]}" build -t e200-release-kernel-base "$project/containers/kernel"
    "${docker[@]}" build --build-arg BASE_IMAGE=e200-release-kernel-base -t e200-release-kernel "$project/containers/kernel-gcc15"
    "${docker[@]}" build -t e200-release-userspace-base "$project/containers/userspace"
    "${docker[@]}" build --build-arg BASE_IMAGE=e200-release-userspace-base -t e200-release-userspace "$project/containers/userspace-next"
    "${docker[@]}" build --build-arg BUILDER_IMAGE=e200-release-userspace -t e200-release-package "$project/containers/package"
fi
for image in e200-release-kernel e200-release-userspace e200-release-package; do
    "${docker[@]}" image inspect "$image" --format '{{.Id}}' > "$work/evidence/$image.txt"
done
# Shell arrays put the command after the image, and Docker options before it.
container() {
    local image=$1; shift
    local -a options=()
    while [[ $1 != -- ]]; do options+=("$1"); shift; done
    shift
    "${docker[@]}" run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e E200_JOBS="$jobs" \
        -v "$project:/project:ro" "${options[@]}" "$image" "$@"
}
if step fetch; then
    container e200-release-userspace -v "$work:/release" -- \
        python3 /project/scripts/build/fetch-release.py /release
fi
if step kernel; then
    container e200-release-kernel -v "$work/baseline:/baseline:ro" -v "$work/next:/next" -- \
        python3 /project/scripts/build/modernization-kernel.py
    container e200-release-kernel --network none -v "$work/next:/next" \
        -e E200_BUILD_ROOT=/next/kernel612 -- sh /project/scripts/build/edge-kernel-in-container.sh
fi
if step userspace; then
    container e200-release-userspace -v "$work/baseline:/work" -- \
        sh /project/scripts/build/iq24-userspace-in-container.sh prepare
    container e200-release-userspace --network none -v "$work/baseline:/work" -- \
        sh /project/scripts/build/iq24-userspace-in-container.sh build
    container e200-release-userspace -v "$work/baseline:/baseline:ro" -v "$work/bash:/work" \
        -e E200_USERSPACE_PROFILE=iq24-bash -- sh /project/scripts/build/modernization-userspace.sh prepare
    container e200-release-userspace --network none -v "$work/baseline:/baseline:ro" -v "$work/bash:/work" \
        -e E200_USERSPACE_PROFILE=iq24-bash -- sh /project/scripts/build/modernization-userspace.sh build
fi
if step iiod; then
    container e200-release-userspace -v "$work/baseline:/work:ro" -v "$work/next:/next" -- \
        sh /project/scripts/build/modernization-libiio.sh
    container e200-release-userspace --network none -v "$work/baseline:/baseline:ro" \
        -v "$work/next:/previous:ro" -v "$work/perf:/perf" \
        -e E200_BUILD_ZEROCOPY=1 -e E200_BUILD_ASYNC=1 -e E200_BUILD_AGGREGATE=1 \
        -e E200_BUILD_SOCKET=1 -e E200_BUILD_PREFETCH=1 -e E200_BUILD_LEGACY_PREFETCH=1 \
        -e E200_BUILD_LEGACY_ASYNC=1 -e E200_BUILD_DUAL_RX=1 -- \
        sh /project/scripts/build/performance-libiio1.sh
fi
if step test; then
    container e200-release-userspace --network none -v "$work/perf:/perf:ro" -- \
        sh /project/tests/host/run-libiio1-transport.sh /perf/libiio1-source
    container e200-release-userspace --network none --ulimit memlock=8388608:8388608 -v "$work/perf:/perf:ro" -- sh -eu -c '
        cc -std=gnu11 -Wall -Wextra -Werror -I/perf/libiio1-source/include /project/tests/host/test_e200_rx_layout.c -o /tmp/layout
        /tmp/layout
        cc -O2 -Wall -Wextra -Werror -pthread /project/tests/host/test_tcp_pipeline.c \
            /project/tests/rf/tcp-pipeline.c /project/tests/rf/tcp-transport.c -o /tmp/pipeline
        /tmp/pipeline'
fi
if step package; then
    container e200-release-package --network none -v "$work:/release" -- \
        python3 /project/scripts/package/release-package.py /release
fi
# Source collection is explicit: firmware generation does not imply distribution clearance.
if [[ $stage == sources ]]; then
    container e200-release-package -v "$work:/release" -- \
        python3 /project/scripts/package/source-materials.py /release
fi
printf '%s\n' "Stage $stage completed. Outputs: $work. New artifacts require hardware qualification."
