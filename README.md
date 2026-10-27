# ANTSDR E200 community firmware

Modern Linux firmware for **ANTSDR E200**, with libiio network streaming and a
Docker build that assembles a complete microSD image. Independent community project.

**Developer preview:** this candidate uses native **libiio 1.0.0 throughout the
firmware**, including local tools and libad9361. Legacy network clients remain
supported; the old library, ABI shim and recovery daemon are removed.
The migrated image passed a full ARM build, SD write/readback, automatic warm
boot, local self-tests and 10-minute single-RX tests at 24 MS/s with both clients.
Physical cold boot of this image remains pending. New SSH sessions during RX
still reproduce overflow; connect before capture. See the
[hardware validation record](docs/native-iio-validation-2026-10-27.md).

## Quick start

Use **Linux x86-64**, Git and a running Docker engine, as a non-root user.
Allow at least **8 GiB RAM, 70 GiB free disk**, Internet access and several hours
for the first build. On macOS/Windows, use a Linux x86-64 build machine or VM.

```sh
git clone https://github.com/enricolorenzoni59/antsdr-e200-fw.git && cd antsdr-e200-fw
./build.sh
```

The script builds its Docker images, fetches pinned sources and verified vendor
boot files, compiles Linux/userspace/iiod, runs native checks and packages the SD.
It requests sudo for Docker only when needed. No Vivado installation is required.

**Output:** `build/image.raw`, with `build/image.raw.sha256`.
Detailed manifests remain under `work/release/package/`.
Logs stay under `work/release/`. The script builds files; writing a card is a
separate step. Use a fresh work directory for a new build; see
[build/resume instructions](docs/release-build.md).

## Write the microSD

Unmount the card's mounted partitions first. Replace `/path/to/your/microsd`
with the **whole microSD device**, not a partition or directory. This erases the
selected card; keep the original recovery card intact.

```sh
sudo dd if=build/image.raw of=/path/to/your/microsd bs=1M conv=fsync status=progress
```

This command is for Linux. After it finishes, eject the card safely and follow
[the E200 SD boot and recovery instructions](docs/recovery.md).

## Firmware comparison

Other project versions checked **2026-09-28**; this project's native-IIO migration
is described separately below. These projects serve different purposes;
this is a source/build comparison, not a performance ranking or binary audit.

| Firmware | Main purpose | Linux | Userspace | Boot / FPGA |
| --- | --- | --- | --- | --- |
| **This project, current candidate** | IIO IQ streaming; initial scope single RX | ADI **6.12.111**, GCC 15 | **Buildroot 2026.08**, BusyBox + Bash; native libiio/iiod **1.0.0**, libad9361 v1 API port | Official E200 v0.39 BOOT.BIN + FPGA; SD, rootfs in RAM |
| [MicroPhase IIO / v0.39](https://github.com/MicroPhase/antsdr-fw-patch) | Original Pluto-derived ANTSDR firmware | ADI **6.1.0** | **Buildroot 2023.02.5**, libiio 0.26 | Vendor U-Boot **2016.07** + FSBL; IIO FPGA |
| [m1nl/e200-fw](https://github.com/m1nl/e200-fw) | Modernized E200 IIO firmware | ADI **6.1.70** | **Buildroot 2025.05.2**, libiio 0.26 | U-Boot **2016.07** + FSBL; rebuilds E200 HDL with Vivado 2023.2 |
| [Tezuka / E200 profile](https://github.com/F5OEO/tezuka_fw) | Multi-board SDR, IIO, Maia-SDR and dashboard | ADI **6.12.77** | **Buildroot 2026.02**, integrated SDR apps | U-Boot **2025.01**; supplied E200 FSBL/FPGA, SD boot |
| [MicroPhase UHD](https://github.com/MicroPhase/antsdr_uhd) | UHD host applications | **5.2.28** | **Buildroot 2020.02.8**, UHD device firmware | U-Boot **2016.07** + FSBL; different UHD FPGA |
| [OpenWiFi, Buildroot path](https://github.com/open-sdr/openwifi) | FPGA-based **802.11 Wi-Fi** | ADI **6.12.0** source pin | **Buildroot 2025.02.11**, OpenWiFi drivers/tools | Xilinx U-Boot **2024.01 / 2024.2**, SPL; Wi-Fi FPGA |
| [MicroPhase PYNQ](https://github.com/MicroPhase/antsdr-pynq) | Python/Jupyter and FPGA overlays | PetaLinux **2022.1** recipe; exact kernel unverified | PYNQ image/Jupyter; exact rootfs version unverified | E200 BOOT.BIN with FSBL/U-Boot; overlay workflow |

Our changes are the modern kernel/rootfs, patched IIO transport, Docker image
assembly and automated checks. **The bootloader and FPGA remain vendor inputs.**
Tezuka already offers E200 release packages and a newer boot stack; our scope
focuses on the documented IIO transport and qualification procedure.
UHD, OpenWiFi and PYNQ have different application stacks and are not drop-in IIO
replacements. [Pinned sources and comparison details](docs/firmware-comparison.md).

## Scope and operation

The native-IIO image sustained **24 MS/s, single RX, I16/Q16** for 10 minutes per
client, without detected DMA overflow after the first startup second. Client
pause/kill/reconnection recovery passed for both libraries. Opening a new SSH
session during capture reproduced DMA overflow; two diagnostic commands over a
connection established beforehand passed a 90-second native RX test.
Connect before capture; other concurrent workloads remain unqualified.
Use 32 kernel buffers:
native libiio 1.0 requests **262,144 samples (1 MiB)**; legacy 0.26 requests
**2,097,152 samples (8 MiB)**. Legacy 1 MiB requests overflowed at that rate.
Client recovery and final reconnections also passed. See the exact image hash
and remaining checks in [qualification status](docs/release-status.md).
TX, dual RX and QSPI flashing are outside the initial release scope.

Development defaults: **192.168.1.10**, SSH **root/analog**, unauthenticated IIO.
Use a trusted receiver LAN and preserve the original recovery card.

## How to change the IP

Edit `board/antsdr-e200/rootfs-overlay/etc/network/interfaces`.
For a **static IP**, use the following, replacing the address and netmask for
your network (optionally add `gateway YOUR_GATEWAY_IP`):

```text
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet static
    address 192.168.1.20
    netmask 255.255.255.0
```

For **DHCP**, replace the file contents with:

```text
auto lo
iface lo inet loopback

auto eth0
iface eth0 inet dhcp
```

DHCP requires a server on the connected network; there is no configured static
fallback. Find the assigned address in your router's leases or through UART
with `ip -4 addr show dev eth0`.

Make the change in a fresh checkout/build tree, run `./build.sh` successfully,
then write the **new** `build/image.raw` to the whole microSD and reboot from it.
Editing `/etc/network/interfaces` on the running E200 is temporary because the
rootfs lives in RAM. A failed rebuild can leave an old image on disk.
The `profile/rootfs/` path used by `antsdr-e200-stream1090` is not read by
this repository.

[Clients](docs/clients.md) · [Build details](docs/release-build.md) ·
[Qualification](docs/release-status.md) · [IIO migration](docs/libiio-migration.md) · [Recovery](docs/recovery.md) ·
[Licensing](docs/licensing.md)

Original project code: **GPL-3.0-or-later**. Third-party components retain their
licenses; see [license scope](LICENSING.md) and [full GPLv3 text](LICENSE).
