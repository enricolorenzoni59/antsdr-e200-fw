#!/usr/bin/env bash
# Build a complete SD image using Docker. Never access a card or the radio.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --help ]]; then
    echo 'Usage: ./build.sh (builds build/image.raw)'
    echo 'Requires Linux x86-64, a non-root user, Git and Docker.'
    echo 'Optional: E200_JOBS=2, E200_RELEASE_WORK=/absolute/new/directory, E200_DOCKER_SUDO=0|1'
    exit 0
fi
[[ $# == 0 ]] || { echo 'Use ./build.sh --help' >&2; exit 2; }
[[ $(uname -s) == Linux && $(uname -m) == x86_64 && $(id -u) != 0 ]] || {
    echo 'Run as a non-root user on Linux x86-64 (a Linux VM is fine).' >&2; exit 1;
}
command -v docker >/dev/null || { echo 'Install and start Docker first.' >&2; exit 1; }
export E200_JOBS=${E200_JOBS:-2}
[[ $E200_JOBS =~ ^[1-9][0-9]*$ ]] || { echo 'E200_JOBS must be a positive integer.' >&2; exit 2; }
if [[ -z ${E200_DOCKER_SUDO+x} ]]; then
    if docker info >/dev/null 2>&1; then export E200_DOCKER_SUDO=0
    else export E200_DOCKER_SUDO=1; fi
fi
case $E200_DOCKER_SUDO in
    0) docker info >/dev/null ;;
    1)
        if ! sudo -n docker info >/dev/null 2>&1; then
            sudo -v
            sudo -n docker info >/dev/null
        fi
        # Later build stages also use sudo -n; preserve authentication during
        # long compilations so they do not fail after the timestamp expires.
        # A command-specific NOPASSWD rule may allow Docker but not sudo -v.
        (while sleep 60; do sudo -n -v 2>/dev/null || true; done) &
        sudo_refresh_pid=$!
        trap 'kill "$sudo_refresh_pid" 2>/dev/null || true' EXIT
        ;;
    *) echo 'E200_DOCKER_SUDO must be 0 or 1.' >&2; exit 2 ;;
esac
work=${E200_RELEASE_WORK:-$project/work/release}
[[ $work == /* ]] || { echo 'E200_RELEASE_WORK must be absolute.' >&2; exit 2; }
mkdir -p "$work"
export E200_RELEASE_WORK=$work
log="$work/build-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
bash "$project/scripts/build/release.sh" all 2>&1 | tee "$log"
test -s "$work/package/sd/e200-sd.img"
(cd "$work/package/sd" && sha256sum -c SHA256SUMS)
mkdir -p "$project/build"
image_tmp=$(mktemp "$project/build/.image.raw.XXXXXX")
cp --reflink=auto --sparse=always "$work/package/sd/e200-sd.img" "$image_tmp"
mv -fT "$image_tmp" "$project/build/image.raw"
(cd "$project/build" && sha256sum image.raw > image.raw.sha256)
printf '\nSD image: %s\nBuild log: %s\n' "$project/build/image.raw" "$log"
