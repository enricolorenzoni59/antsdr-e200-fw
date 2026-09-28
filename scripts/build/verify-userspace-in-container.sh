#!/bin/sh
# Filesystem and ARM userspace checks; no boot or hardware access.
set -eu
root=${E200_BUILD_ROOT:-/work}
output=$root/edge-userspace-output
target=$output/target
images=$output/images
evidence=$root/evidence
mkdir -p "$evidence"
qemu-arm -L "$target" "$target/bin/busybox" echo 'ARM BusyBox execution: PASS' \
    > "$evidence/arm-userspace-smoke.log"
qemu-arm -L "$target" "$target/usr/bin/python3" --version \
    >> "$evidence/arm-userspace-smoke.log" 2>&1
"$output/host/bin/mkimage" -l "$images/rootfs.cpio.uboot" > "$evidence/ramdisk-header.txt"
readelf -h "$target/bin/busybox" > "$evidence/busybox-elf-header.txt"
e2fsck -f -n "$images/rootfs.ext4" > "$evidence/ext4-check.log" 2>&1
# debugfs cat does not follow the /etc/os-release symlink.
debugfs -R 'cat /usr/lib/os-release' "$images/rootfs.ext4" \
    > "$evidence/rootfs-os-release.txt" 2> "$evidence/debugfs.log"
grep -q '^ID=buildroot' "$evidence/rootfs-os-release.txt"
cpio -it < "$images/rootfs.cpio" > "$evidence/cpio-files.txt" 2> "$evidence/cpio-check.log"
for entry in bin/busybox usr/bin/python3 etc/network/interfaces etc/default/dropbear; do
    grep -Eq "^(\\./)?$entry\$" "$evidence/cpio-files.txt"
done
printf '%s\n' 'ROOTFS CHECK PASS: ext4 integrity, CPIO contents, ARM BusyBox and Python under QEMU.'
printf '%s\n' 'This is userspace emulation, not board boot or RF validation.'
