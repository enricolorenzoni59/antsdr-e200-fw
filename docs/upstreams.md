# Upstream components and update watch

Snapshot from the `v0.1.0-rc1` build (2026-11-06). Versions are the exact
ones in the image, not only the lock-file intent.

## Pinned components

| Component | Current | Latest available | Suggested action |
| --- | --- | --- | --- |
| Linux kernel (ADI 6.12) | 6.12.111 | **6.12.115** (latest 6.12.y) | Bump the stable patch series: four patches, no config change. |
| Linux latest LTS | 6.12.111 | 6.18.61 | Major migration: ADI base, E200 board patches and vendor FPGA need a port and full qualification. Defer. |
| Buildroot | 2026.08 | **2026.08.1** (2026.11 is on master) | Bump to the stable patch release; it also brings Python 3.14.8. |
| Userspace toolchain | Arm GNU 14.2.rel1 | **15.2.rel1** | Already selectable with `E200_USERSPACE_TOOLCHAIN=15.2`; run the full runtime tests before changing the lock. |
| Kernel compiler | GCC 15.2.0 (Ubuntu 26.04 snapshot) | GCC 15.3.0 | Tied to the pinned Ubuntu snapshot; no direct update. |
| libiio | v1.0.0 | v1.0.0 | None: already the latest release. |
| libad9361-iio | `7d8e7ca` | `7d8e7ca` (upstream main) | None today; review new main commits before moving. |
| Vendor BSP (BOOT.BIN/FPGA) | v0.39 | v0.39 | No newer versioned MicroPhase BSP. `antsdr_mesh` is a separate firmware line, not a drop-in. |
| Ubuntu builder base | 26.04 `20260923T000000Z` | latest 26.04 snapshot | Keep the dated snapshot for reproducibility; change only with a full rebuild and requalification. |

## Buildroot packages

`2026.08` is the pinned build; `2026.08.1` is the latest stable patch;
`master` is the next feature release (2026.11).

| Package | 2026.08 (current) | 2026.08.1 | master |
| --- | --- | --- | --- |
| BusyBox | 1.38.0 | 1.38.0 | 1.38.0 |
| Dropbear | 2026.94 | 2026.94 | 2026.94 |
| Python 3 | 3.14.7 | 3.14.8 | 3.14.10 |
| Bash | 5.2.37 | 5.2.37 | 5.2.37 (5.3 upstream, not packaged yet) |
| iproute2 | 7.1.0 | 7.1.0 | 7.3.0 |
| ethtool | 7.1 | 7.1 | 7.2 |
| iperf3 | 3.21 | 3.21 | 3.22 |
| zstd | 1.5.7 | 1.5.7 | 1.5.7 |
| libxml2 | 2.15.3 | 2.15.4 | 2.15.4 |
| libffi | 3.8.0 | 3.8.0 | 3.8.0 |
| ncurses | 6.6-20251231 | 6.6-20251231 | 6.6-20251231 |
| readline | 8.3 | 8.3 | 8.3 |

## Order of work

1. **Low risk:** kernel 6.12.115 and Buildroot 2026.08.1. Both are patch-level;
   rebuild, check the image hash and repeat the existing host/runtime tests.
2. **Medium risk:** Arm GNU 15.2.rel1 for userspace. The build already supports
   it; the change needs a full runtime pass (iio, libad9361, Python, Bash).
3. **When 2026.11 is released:** move Buildroot and pick up Python 3.14.10,
   iproute2 7.3.0, ethtool 7.2, iperf3 3.22 and libxml2 2.15.4.
4. **Later:** kernel 6.18 LTS, only with an ADI/E200 port and hardware
   qualification.
5. **No action:** vendor BSP v0.39, Ubuntu 26.04 snapshot, libiio v1.0.0,
   libad9361 main, BusyBox, Dropbear, zstd, libffi, ncurses, readline.

## Watchers

- **Dependabot** (`.github/dependabot.yml`) runs weekly on Monday morning for
  `github-actions` (the pinned action SHAs) and `pip`
  (`requirements-test.txt`). It opens grouped PRs and the normal host checks
  still gate them.
- **Upstream dependency watch** (`.github/workflows/upstream-watch.yml`) runs
  every Monday at 06:00 UTC. It compares the lock files and Buildroot recipes
  with kernel.org, Buildroot, libiio, libad9361 and MicroPhase, and creates or
  updates a single issue titled `Upstream dependency watch`. It never builds
  firmware and does not modify the repository.
- Dependabot cannot track the kernel, Buildroot, libiio, libad9361, the Arm
  toolchain or the vendor BSP because they are pinned by lock files and
  Buildroot recipes rather than a supported package manifest. That is why the
  second watcher exists.
- The Docker base image is intentionally pinned by digest and a dated package
  snapshot. Dependabot's Docker ecosystem is not enabled: an automatic digest
  update would silently change the whole package set and break the recorded
  reproducibility.

Run the second watcher manually with:

```sh
gh workflow run upstream-watch.yml --repo enricolorenzoni59/antsdr-e200-fw
```
