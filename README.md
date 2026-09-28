# ANTSDR E200 community firmware

Modern Linux firmware for **ANTSDR E200**, with libiio network streaming and a
Docker build that assembles a complete microSD image. Independent community project.

**Developer preview:** a clean full-image build, microSD write/readback, automatic
warm and physical cold boot, software rollback and 10-minute 24 MS/s tests with both clients passed.
Opening new SSH sessions during capture reproduced native RX overflow; connect before capture.
Two clean builds produced identical images using the same cached Docker builders.
The repository stays private until the publication review is complete.

## Quick start

Use **Linux x86-64**, Git and a running Docker engine, as a non-root user.
Allow at least **8 GiB RAM, 70 GiB free disk**, Internet access and several hours
for the first build. On macOS/Windows, use a Linux x86-64 build machine or VM.
Access to this private repository must already be configured in Git.

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

Source versions checked **2026-09-28**. These projects serve different purposes;
this is a source/build comparison, not a performance ranking or binary audit.

| Firmware | Main purpose | Linux | Userspace | Boot / FPGA |
| --- | --- | --- | --- | --- |
| **This project** | IIO IQ streaming; initial scope single RX | ADI **6.12.111**, GCC 15 | **Buildroot 2026.08**, BusyBox + Bash; patched iiod 1.0, libiio 0.26 retained | Official E200 v0.39 BOOT.BIN + FPGA; SD, rootfs in RAM |
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

The tested image sustained **24 MS/s, single RX, I16/Q16** for 10 minutes per
client, without detected DMA overflow after the first startup second. A further
10-minute native test after rollback/reinstallation also passed. Opening new SSH
sessions during capture caused native RX overflow. With SSH connected beforehand,
19 timed diagnostic commands passed during a further 10-minute native test.
Connect before capture; other concurrent workloads remain unqualified.
Use 32 kernel buffers:
native libiio 1.0 requests **262,144 samples (1 MiB)**; legacy 0.26 requests
**2,097,152 samples (8 MiB)**. Legacy 1 MiB requests overflowed at that rate.
Client recovery and final reconnections also passed. See the exact image hash
and remaining checks in [qualification status](docs/release-status.md).
TX, dual RX and QSPI flashing are outside the initial release scope.

Development defaults: **192.168.1.10**, SSH **root/analog**, unauthenticated IIO.
Use a trusted receiver LAN and preserve the original recovery card.

[Clients](docs/clients.md) · [Build details](docs/release-build.md) ·
[Qualification](docs/release-status.md) · [Recovery](docs/recovery.md) ·
[Licensing](docs/licensing.md)

Original project code: **GPL-3.0-or-later**. Third-party components retain their
licenses; see [license scope](LICENSING.md) and [full GPLv3 text](LICENSE).
