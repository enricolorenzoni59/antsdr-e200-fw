# Boot and recovery

Keep the original working microSD unchanged. Write `build/image.raw` only to a
separate, identified test card using the README command. The complete image
already contains the partition table and FAT boot partition.

With power disconnected, insert the test card and select SD boot using the
hardware selector documented for your E200 revision. Connect UART at
115200 baud, 8N1 before applying power and retain the complete startup output.
Verify Ethernet at 192.168.1.10 and the actual running kernel/daemon versions.
A cold-boot test requires removal of every power source, not merely a reboot.

For rollback, power down, restore the original card and its original boot
selector position. This project does not require QSPI writes or saved U-Boot
environment changes. Do not use Pluto USB-DFU instructions for E200; consult
[MicroPhase's E200 instructions](https://github.com/MicroPhase/antsdr-fw-patch).

Automatic warm boot and software rollback/reinstallation passed on the test
board; see [qualification status](release-status.md) for the exact image and
scope. The test temporarily enabled SD0 in a RAM-only device tree, restored a
verified backup of the affected card region, booted the previous firmware,
then reinstalled and read back the candidate image. No saved U-Boot environment
or QSPI writes were needed. This maintenance procedure requires a working
bootloader and RAM-bootable firmware; the original card remains the fallback
when the test card cannot boot. Physical cold-boot qualification is still pending.
