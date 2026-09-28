# E200 firmware comparison: source references

Checked 2026-09-28. The README compares source recipes, not the runtime contents
of downloaded images. No alternative firmware was built or benchmarked in this
review. A newer version alone does not establish better performance or support.

## Direct IIO alternatives

**MicroPhase antsdr-fw-patch:** current master
[`7b35aa0`](https://github.com/MicroPhase/antsdr-fw-patch/tree/7b35aa04874dcae529014aa09711ad4564cb6929)
still selects Pluto commit
[`9e90bce`](https://github.com/analogdevicesinc/plutosdr-fw/tree/9e90bce43f849882cd43c20a08effca132790fb3),
also used by the v0.39 baseline. Its component gitlinks select
[Linux 6.1.0](https://github.com/analogdevicesinc/linux/blob/f3da30df60047dc5a0b8fa8c640be774e0f784d9/Makefile),
[Buildroot 2023.02.5](https://github.com/analogdevicesinc/buildroot/blob/e783aadccebad3413b3d60fcfe98a25eb395d839/Makefile),
and [U-Boot 2016.07](https://github.com/analogdevicesinc/u-boot-xlnx/blob/90401ce9ce029e5563f4dface63914d42badf5bc/Makefile).
Our release recipe reuses the official v0.39 BOOT.BIN and FPGA, with hashes in
[the vendor lock](../configs/vendor-v039-artifacts.json). It does not modernize
that bootloader or rebuild FPGA logic. The vendor's separate mesh release is not
the IIO baseline.

**m1nl/e200-fw:** an especially relevant E200 IIO alternative, inspected at
[`0d13eda`](https://github.com/m1nl/e200-fw/tree/0d13eda1b4cb16e4efca89f8d3631543838ac5df).
Follow its gitlinks, rather than the current heads of its component branches:

| Component | Pinned source |
| --- | --- |
| Linux 6.1.70 | [01e8578 / Makefile](https://github.com/m1nl/analogdevicesinc-linux/blob/01e857869eba33fed58e88f9c5691d9fb329c34f/Makefile) |
| Buildroot 2025.05.2 | [7fd4805 / Makefile](https://github.com/m1nl/buildroot/blob/7fd48054c89bf41e3500fb93e23a5a104043b387/Makefile) |
| libiio 0.26 | [package recipe](https://github.com/m1nl/buildroot/blob/7fd48054c89bf41e3500fb93e23a5a104043b387/package/libiio/libiio.mk) |
| U-Boot 2016.07 | [f6e206c / Makefile](https://github.com/m1nl/u-boot-xlnx/blob/f6e206c06c51b0e40f260afec2d68ef1e16fd9af/Makefile) |
| E200 HDL | [ea842d3](https://github.com/m1nl/analogdevicesinc-hdl/tree/ea842d3c935a6ef513c072241aca856affdaa399) |

Its [top-level Makefile](https://github.com/m1nl/e200-fw/blob/0d13eda1b4cb16e4efca89f8d3631543838ac5df/Makefile)
selects Vivado 2023.2 and builds HDL, FSBL and BOOT.bin. The
[E200 defconfig](https://github.com/m1nl/buildroot/blob/7fd48054c89bf41e3500fb93e23a5a104043b387/configs/zynq_e200_defconfig)
selects an internal GCC 13 toolchain and glibc. There were no GitHub releases at
inspection. This is not evidence that it does not work; hardware qualification
and sustained-RX performance were not verified here. Relative to that project,
our selected changes are Linux 6.12.111, Buildroot 2026.08, patched iiod 1.0 and
Docker assembly from existing vendor boot/FPGA inputs. No performance superiority
is claimed, and no implementation files were imported from this review.

## Tezuka: a direct modern SDR alternative

**F5OEO/tezuka_fw**, inspected at
[`44cdd7a`](https://github.com/F5OEO/tezuka_fw/tree/44cdd7a8de56468380e1fd3324cb2ce63f167273),
explicitly maps E200 to `e200_maiasdr_defconfig` in
[boards.json](https://github.com/F5OEO/tezuka_fw/blob/44cdd7a8de56468380e1fd3324cb2ce63f167273/boards.json).
Its [E200 configuration](https://github.com/F5OEO/tezuka_fw/blob/44cdd7a8de56468380e1fd3324cb2ce63f167273/configs/e200_maiasdr_defconfig)
selects [ADI Linux 6.12.77](https://github.com/analogdevicesinc/linux/blob/0d285126d15a9ea77f1c5bbfd2a4a6c40dfd648e/Makefile)
and [ADI U-Boot 2025.01](https://github.com/analogdevicesinc/u-boot-xlnx/blob/a09d2660433d3d1ade6a14a82b21a13c2bbb3821/Makefile).
[buildroot.version](https://github.com/F5OEO/tezuka_fw/blob/44cdd7a8de56468380e1fd3324cb2ce63f167273/buildroot.version)
pins Buildroot 2026.02 with archive hashes. It supplies E200 FSBL/XSA files and
[extracts the FPGA bitstream](https://github.com/F5OEO/tezuka_fw/blob/44cdd7a8de56468380e1fd3324cb2ce63f167273/package/board-fpga/board-fpga.mk)
from the selected board XSA.

Tezuka includes IIO, Maia-SDR and a dashboard. Its latest release at inspection,
[v0.3.21](https://github.com/F5OEO/tezuka_fw/releases/tag/v0.3.21), includes
`tezuka-e200-v0.3.21-833d536.zip`. The table describes the inspected main-branch
recipe, not an audit of this older release ZIP. Tezuka's advertised 8-bit
streaming rates are not directly comparable with our I16/Q16 measurements.

This is a direct alternative worth evaluating, not merely a reference project.
It already offers a newer boot stack and broader integrated applications.
Our narrower aim is a Docker-built image with explicit IIO buffer settings,
transport regression tests and exact-image qualification. Those aims do not
establish better reliability or throughput than Tezuka; a controlled comparison
on matching hardware, formats and workloads would be needed.

## Different application stacks

**MicroPhase UHD**, inspected at
[`b5ebd04`](https://github.com/MicroPhase/antsdr_uhd/tree/b5ebd04a5f405ac3102a772e5d1e8f1be21a7dc3):
[Linux Makefile](https://github.com/MicroPhase/antsdr_uhd/blob/b5ebd04a5f405ac3102a772e5d1e8f1be21a7dc3/firmware/linux/Makefile)
reports 5.2.28; [Buildroot](https://github.com/MicroPhase/antsdr_uhd/blob/b5ebd04a5f405ac3102a772e5d1e8f1be21a7dc3/firmware/buildroot/Makefile)
reports 2020.02.8; [U-Boot](https://github.com/MicroPhase/antsdr_uhd/blob/b5ebd04a5f405ac3102a772e5d1e8f1be21a7dc3/firmware/u-boot-xlnx/Makefile)
reports 2016.07. It pairs its own FPGA/device firmware with a UHD host driver;
it is not a replacement iiod service.

**OpenWiFi**, inspected at
[`2f112f0`](https://github.com/open-sdr/openwifi/tree/2f112f0b40d54b3fd6c049d1437c9f967d7a8ef2):
the [Buildroot guide](https://github.com/open-sdr/openwifi/blob/2f112f0b40d54b3fd6c049d1437c9f967d7a8ef2/doc/img_build_instruction/buildroot/README.md)
documents Buildroot 2025.02.11. The [actual defconfig](https://github.com/open-sdr/openwifi/blob/2f112f0b40d54b3fd6c049d1437c9f967d7a8ef2/buildroot-external/configs/openwifi_common_defconfig)
selects ADI Linux `40201ab` ([6.12.0 Makefile](https://github.com/analogdevicesinc/linux/blob/40201abd70d8f7848547a09fc7e366fba064483c/Makefile))
and Xilinx U-Boot `xlnx_rebase_v2024.01_2024.2`, with SPL. Its E200 support serves
802.11 Wi-Fi FPGA/driver operation. The table refers only to this Buildroot path;
the project also offers other image-building paths.

**MicroPhase PYNQ**, inspected at
[`8468cb5`](https://github.com/MicroPhase/antsdr-pynq/tree/8468cb5f1e75211f58a1efe1fd123b60e2ce5bb1):
the [README](https://github.com/MicroPhase/antsdr-pynq/blob/8468cb5f1e75211f58a1efe1fd123b60e2ce5bb1/README.md)
describes PetaLinux 2022.1 and Vivado/Vitis 2021.1, Jupyter and overlays.
The [boot recipe](https://github.com/MicroPhase/antsdr-pynq/blob/8468cb5f1e75211f58a1efe1fd123b60e2ce5bb1/e200_boot_gen/Makefile)
assembles FSBL, bitstream, U-Boot and device tree. Exact kernel, U-Boot and
rootfs versions of its downloadable images were not verified; tool-suite names
must not be presented as those component versions.
