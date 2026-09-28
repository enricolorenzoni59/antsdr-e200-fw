# Licensing audit status

No binary release is cleared for redistribution yet. Original project code and documentation are
GPL-3.0-or-later unless a file or component specifies another license.
See [the license scope](../LICENSING.md); downloaded components and third-party
patch context retain their own notices and licenses.

The build collects Buildroot legal-info; this is not a complete firmware SBOM.

For the tested `f3e6be04aa72dfee4fc1de5f5bd7553bd7767760` build, the source
collector completed on 2026-09-28: 246 inventoried files, 932,367,180 bytes,
with every inventory SHA256 checked. The Buildroot manifests list 15 target
and 36 host packages; components assembled outside Buildroot need separate
reconciliation. The only target package whose own license field is `unknown`
is Arm GNU 14.2.rel1. Its source snapshot, license text and upstream manifest
are included separately. Collection and checksum checks do not close the
runtime license review or vendor binary redistribution review.

The inventory was extended directly from the exact SD image: all three FAT
files, four FIT payloads, three BOOT partitions and 747 regular rootfs files
are covered by a firmware-wide review SPDX 2.3 document. Its 757 file entries
and 35 component groups passed schema and SPDX-tools validation; all rootfs
hashes match the earlier inventory. A companion inventory records 347 symlinks
and counts the remaining nonregular entries. Package provenance does not by
itself conclude individual file licenses.

All 14 target source archives and 19 notice files declared by Buildroot were
located and hashed. The remaining target archive is the Arm binary SDK; its
corresponding source snapshot is collected separately. Including kernel,
libiio 1.0, zstd, project and Arm runtime texts gives 33 software notice texts
for review. Kernel patches, added files, Buildroot/project sources and build
configuration are also present in the collected materials. Raw inventories and
notice bundles remain outside Git while redistribution review is open.
The Arm runtime includes glibc 2.40; its source version matches the collected
snapshot, which also contains GCC sources and runtime-exception notices.

Outstanding work before redistribution:

- Finish component-level license and notice review, including the separate
  Arm runtime sources rather than treating the binary SDK as source code.
- Resolve the corresponding U-Boot source and changes for the downloaded
  BOOT.BIN, which is outside Buildroot's package graph.
- Audit MicroPhase-origin additions and the specific FPGA/FSBL artifacts. A public
  download URL alone is not a redistribution license.
- Complete the vendor source/notice collection and release bundle. The validated
  review SPDX deliberately retains unresolved license conclusions; structural
  validation and available source archives are not redistribution clearance.

The public E200 schematic has restrictive copying terms and is not redistributed
here. AMD/Xilinx tool installations are neither downloaded by project scripts nor
included in the container. The official firmware reference archive stays in
ignored local storage, with provenance and hashes recorded separately.

## Source-only developer preview (2026-09-28)

The repository contains original build tools, patches with retained
provenance/notices, configurations and release tests. Downloaded
component trees, AMD tools, vendor boot/FPGA binaries and generated SD/FIT images
are excluded from Git. The public recipe fetches the official archive for local
builds and verifies the archive and individual BOOT.BIN/bitstream hashes.

The actual v0.39 `e200.zip` contains `e200/build/LICENSE.html` (SHA256 recorded
in `configs/vendor-v039-artifacts.json`). Its package inventory names Linux,
U-Boot, libiio and other old rootfs components, including an unknown external
toolchain license entry. It is an inventory of the vendor image, not our new
Buildroot 2026.08 rootfs or a complete component-level FPGA/FSBL inventory.
Its inherited written-offer text assumes the recipient built from source;
it must not be copied as our own binary distribution statement.

For the new image collect these separately:

| Input | Material needed alongside a binary release |
| --- | --- |
| Modern rootfs | Its own Buildroot legal-info, source archives, patches and config |
| Kernel outside Buildroot | Exact ADI source, stable changes, local patches and build config |
| iiod1 outside Buildroot | Pinned libiio source, applied patch stack, helper sources and zstd sources/notices |
| Official BOOT.BIN and FPGA | Artifact provenance plus corresponding boot/FSBL/HDL notices and source inventory |
| Build machinery | This repository snapshot and container/toolchain identity |

The source preview and local build path do not declare the binary audit closed.
No automatic CI or GitHub release job uploads firmware binaries.

## Vendor source review (2026-09-28)

The [vendor v0.39 tree](https://github.com/MicroPhase/antsdr-fw-patch/tree/58b8018d596121c220f30e00749bafbe251744a6)
pins `plutosdr-fw` at `9e90bce43f849882cd43c20a08effca132790fb3`, whose
U-Boot and HDL pins are respectively
`90401ce9ce029e5563f4dface63914d42badf5bc` and
`065c8f186ef87ff049d279ed5859ee8d97d91808`. The vendor patch stack must also
be included when reconstructing sources; the pins alone are insufficient.

The pinned SD BOOT.BIN was parsed using the
[official Zynq boot-header definitions](https://github.com/Xilinx/bootgen/tree/d93c3fa6e6ef8aa1d4fb4532c58ed4a5efa8804e/zynq/include).
Its boot/partition header checksums pass. Its three partitions contain FSBL,
FPGA and U-Boot: the FSBL and U-Boot payloads exactly match the loadable segments
of the archive's `fsbl.elf` and `u-boot.elf`. The FPGA payload matches
`system_top.bit` after reversing bytes within each 32-bit word and adding five
padding words. This identifies binary inputs; it does not establish their licenses.

A preserved Vivado 2023.2 build from 2026-09-19 was also rechecked: the pinned
HDL plus vendor patch produced the same configuration payload SHA256 as the
official bitstream (`05f2b0709aabbec1576660f59030cb3565398b80e9b7d6e4420bdc382ad2ed03`).
The complete `.bit` files differ in timestamp headers. This is historical build
evidence, not a new Vivado run, full FPGA timing closure or redistribution clearance.

| Component | Evidence and remaining work |
| --- | --- |
| U-Boot | The packaged boot banner identifies the pinned revision with local changes. A board patch is available, but complete correspondence between the shipped binary and published changes remains unverified. |
| FSBL | The release archive includes source and generated build files. Most top-level source files carry MIT SPDX notices; `md5.c`, listed in the generated build inputs, instead carries Eric Young's SSLeay notice. Preserve its distinct terms and review the BSP dependencies. |
| FPGA HDL | ADI files carry their own dual-license notices. The vendor VCXO patch includes Ettus files `ad5662_auto_spi.v` and `b205_ref_pll.v` marked LGPL-3.0-or-later. Their source and obligations require separate review. |
| Vendor HDL additions | `axi_vcxo_ctrl_v1_0.v`, `axi_vcxo_ctrl_v1_0_S00_AXI.v` and `ltc2630_spi.v` have no license declaration in the published patch; the vendor patch repository has no root license file at this tag. Obtain clarification before clearing binary redistribution. |

These findings concern the downloaded vendor inputs. This project's GPL grant
does not relicense them, and the presence of source in an archive does not by
itself establish complete corresponding source or permission for every input.

## Arm GNU 14.2 material located

The pinned compiler archive includes `license.txt` (SHA256
`9b47c67a1d2421fa5724e2bfd9e2be03f399ade15273b6e38a8f2a3c9bfe31d6`) and
`14.2.rel1-x86_64-arm-none-linux-gnueabihf-manifest.txt` (SHA256
`abc8ce67fb380f88a64c581a02b5fec735ad66dc456877264ff92878453fec10`).
Buildroot's `unknown` entry reflects missing package metadata; it does not mean
these documents are absent from the downloaded toolchain.

The official Arm corresponding-source snapshot is available at
[the 14.2.rel1 source archive](https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/srcrel/arm-gnu-toolchain-src-snapshot-14.2.rel1.tar.xz).
Its [published SHA256](https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/srcrel/arm-gnu-toolchain-src-snapshot-14.2.rel1.tar.xz.sha256asc)
is `e6405f20f8a817a50d92dbf7974d0ee77708dfdf9e79900a59c5d343b464ef9c`;
the downloaded snapshot was verified against it. The collector below preserves
these materials alongside the new rootfs legal-info, kernel sources/changes,
Buildroot and br2-external trees, prepared libiio sources and zstd archive.

After the software build, from a clean Git checkout:

```sh
E200_DOCKER_SUDO=1 bash scripts/build/release.sh sources
```

Output: `work/release/package/source-materials/`, with a hashed inventory.
Source archives and patches are review materials, not a declaration that the
remaining vendor BOOT.BIN/FSBL/FPGA review or runtime license inventory is complete.
Project files are selected from Git's tracked list; untracked local files are
not swept into the source archive. A dirty checkout is rejected.
