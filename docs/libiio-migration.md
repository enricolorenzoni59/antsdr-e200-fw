# Native libiio 1.0 migration

The candidate builds all IIO libraries and programs against libiio **1.0.0**.
It is not yet a hardware-qualified firmware image. The previous image's boot,
rollback and RX results remain historical evidence in [release status](release-status.md).

## Runtime and source identities

| Component | Selected source / installation |
| --- | --- |
| libiio | `v1.0.0`, commit `9a929664fd3effa500430626803ac59ecf2f4ed3`; `/usr/lib/libiio.so.1` |
| libad9361 | Upstream v1 API port, commit `7d8e7cadd07636cafb7a87d6bcdcc4dd4fcca9b3`; linked to libiio ABI 1 |
| iiod | The same libiio source plus the existing E200 transport patch stack; `/usr/sbin/iiod` |
| Local CLI | Native `iio_info`, `iio_attr`, `iio_rwdev` and the other v1 utilities |

Both Buildroot stages install the recipes under `profiles/native-iio/recipes`,
including archive and license hashes. The existing SDK14 toolchain and kernel
selection are unchanged. The libad9361 library retains its own 0.4 version and
`libad9361.so.0` name; that is independent of the libiio ABI it uses.

The old E200 v0 RX patch is no longer selected. The installer removes the known
v0-only Buildroot Python patch only after checking its Git blob identity, and
refuses unexpected package patches. Historical profile files and source locks
are not evidence that libiio v0 is included in the selected release build.

The final overlay replaces the daemon and native libiio/zstd files directly in
`/usr`. It creates no `/opt/e200/libiio1` directory, exports no private library
path and retains no `iiod-0.26`. The native ABI checker scans all ELF files in
each Buildroot target and the final CPIO. It rejects v0 libraries/tools,
dependencies on `libiio.so.0`, missing native consumers and invalid required
symlinks. Packaging also checks input hashes and preservation of unrelated
CPIO members before writing output.

## Compatibility

`LIBIIO_COMPAT=OFF` disables the shim for old local binaries. Applications on
the E200 must use the v1 API and ABI. The self-test uses `iio_rwdev -u local:`;
the old `iio_readdev`/`iio_writedev` executables are absent.

`WITH_IIOD_V0_COMPAT=ON` separately retains legacy network-protocol support.
A PC using libiio 0.26 can still connect without an old library on the board.
The existing native and legacy transport helpers remain in the daemon.
See the [upstream API/ABI notes](https://github.com/analogdevicesinc/libiio/releases/tag/v1.0.0)
and [tool migration guide](https://analogdevicesinc.github.io/libiio/main/tools_migration/).

## Validation on 2026-10-26

| Check | Result |
| --- | --- |
| Python regressions on macOS ARM | 34 passed, 1 Linux-only test skipped, 5 subtests passed |
| Archive/license hashes | Verified, including the exact GitHub archive URLs used by Buildroot |
| Recipe installer | Repeated installation and exact obsolete-patch removal passed; modified patch refused |
| Native macOS libraries and utilities | Built libiio without its ABI shim and built libad9361 against ABI 1; `iio_rwdev --version` reported 1.0.0 |
| Hardware-free libad9361 tests | FilterDesignerTest and GenerateRatesTest passed |
| Linux Python regressions | 35 passed, including real ELF dependency acceptance/rejection |
| Linux native stack | Patched daemon, v1 CLI/library and pinned libad9361 compiled with the actual recipe options; all 11 installed ELF files passed the ABI check |
| Transport sanitizers, RX layout and pipeline | Passed in Linux CI |
| Full ARM Buildroot/SD image | Pending; local host is macOS ARM without Docker |
| New E200 cold boot, recovery and RX | Pending; no board was accessed |

Linux results above are recorded on implementation commit `63c98dc` in
[this CI run](https://github.com/enricolorenzoni59/antsdr-e200-fw/actions/runs/40300400750).
Native compilation uses the target recipe options, but does not exercise
Buildroot's complete ARM dependency graph, the ARM loader, device access or RF.

## Remaining qualification

Use a **fresh** work directory on Linux x86-64 with Docker and the documented
disk/RAM capacity. Old build outputs are not suitable for this migration.

```sh
E200_RELEASE_WORK="$PWD/work/native-v1-release" ./build.sh
```

Record the exact commit, builder identities, image hash and native ABI reports.
The baseline and Bash reports are in their respective `evidence/native-iio.json`
files; the final CPIO report is in `package/rootfs/manifest.json`.
Regenerate legal-info and source materials for the new component set.

Before qualifying the image, repeat cold/warm boot, recovery, bounded local
self-test and sustained single-RX reception with both native and legacy
network clients. Recheck client failure/reconnection and the known new-SSH-session
overflow condition. This migration makes no claim to fix that condition or to
qualify TX or dual RX. Preserve the previous recovery image separately.
