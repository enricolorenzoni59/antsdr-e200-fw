# Build the selected public candidate

Status: end-to-end clean build qualification in progress. The public workflow
creates a new artifact; the historical laboratory image is not a substitute.

Host regression checks run on standard GitHub-hosted runners. The optional
manual full-build workflow requires a self-hosted Linux x86-64 runner labeled
`e200-build` with Docker, at least 8 GiB RAM and 70 GiB free disk. Registering that
runner is separate administration; no full build runs automatically on pushes.

Run `./build.sh` on Linux x86-64. It detects Docker access, uses two jobs by
default, preserves a build log and verifies the packaged checksums.
The default output is
`build/image.raw`, copied from the verified package, with `build/image.raw.sha256`.
Set `E200_RELEASE_WORK` to an absolute, new work directory to isolate a build.
No prior laboratory artifact, proprietary tool installation or SSH access is
required. The official vendor archive is fetched directly and checked against
`configs/vendor-v039-artifacts.json`; no downloaded boot binaries are in Git.

The stages are also individually available:

```sh
E200_DOCKER_SUDO=1 bash scripts/build/release.sh images
E200_DOCKER_SUDO=1 bash scripts/build/release.sh fetch
E200_DOCKER_SUDO=1 bash scripts/build/release.sh kernel
E200_DOCKER_SUDO=1 bash scripts/build/release.sh userspace
E200_DOCKER_SUDO=1 bash scripts/build/release.sh iiod
E200_DOCKER_SUDO=1 bash scripts/build/release.sh test
E200_DOCKER_SUDO=1 bash scripts/build/release.sh package
```

Run stages in order. Userspace preparation and packaging deliberately refuse
existing outputs. Resume a failed stage only after checking its log; use a new
work directory for an independent rebuild. Source revision mismatches never
trigger an automatic reset of an existing checkout.

The kernel source combines the pinned ADI commit, individually hashed stable
updates, reviewed conflict resolutions, E200 board patches and cached RX.
The baseline Buildroot stage supplies the SDK14 radio stack; the separate Bash
stage builds 2026.08 userspace. Patched iiod1 and its private libraries are
assembled into the CPIO without replacing the original libiio 0.26 ABI.

Kernel compilation, the userspace build after source download, candidate iiod
compilation, native checks and final packaging run with Docker networking off.
Source preparation and initial dependency fetches require Internet access.
Docker image IDs, source fingerprints and output hashes identify the result.
Pinned source and package versions alone do not prove byte reproducibility;
a separate clean replay must verify that property for each release.

## Outputs

The default command publishes `build/image.raw` in the repository root after
checking package hashes. It does not write any block device; see the README
for the separate `dd` command. Intermediate paths below are under `work/release/`.

- `package/sd/e200-sd.img`: complete 129 MiB microSD image.
- `package/sd/SHA256SUMS` and `manifest.json`: structural checks and identities.
- `package/build-manifest.json`: source fingerprints and component locks.
- `package/rootfs/`: consolidated CPIO and retained-daemon overlay manifest.
- `bash/edge-userspace-output/legal-info/`: Buildroot licensing collection.
- `evidence/`: container identities; capture command logs when invoking the build.

The shared historical packager also creates QSPI payload files. They are
experimental byproducts, outside this release scope; do not flash them.

The official v0.39 BOOT.BIN SHA256 is
`d3b30bc1bdda7872d05b976e7ec2841a40287a85272003bee1bf7d4fdae8ccb0`.
The earlier laboratory package used a different locally built BOOT.BIN.
The public build's hash checks do not make it the same hardware-qualified image.

## Distribution

No binary upload is automatic. Before distributing images, complete exact-image
qualification and collect corresponding component sources, patches, build
configuration and license notices. Buildroot legal-info does not include all
external kernel/boot/FPGA inputs. See [licensing](licensing.md).

To collect the corresponding software sources after a successful build, use
`E200_DOCKER_SUDO=1 bash scripts/build/release.sh sources` from a clean Git
checkout and the same `E200_RELEASE_WORK`. This is an explicit distribution
preparation step, separate from SD generation. It verifies and includes Arm's
297 MiB corresponding-source archive; allow additional disk space for sources.
See [licensing](licensing.md) for the remaining vendor artifact review.
