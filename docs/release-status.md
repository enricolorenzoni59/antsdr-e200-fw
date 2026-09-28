# Qualification status

Developer preview. The repository remains private during publication review.

| Check | Status |
| --- | --- |
| Kernel, rootfs, patched iiod and SD packaging | PASS on commit `f3e6be04aa72dfee4fc1de5f5bd7553bd7767760` |
| Default `./build.sh` from a new clone | PASS in 6,631.222 seconds (1 h 50 min 31 s); fresh project outputs, cached Docker image layers |
| Host tests | Image integrity guards, board self-test, transport sanitizers, 104 RX layout checks and pipeline tests in CI |
| microSD write/readback | PASS: all 129 MiB written and read back with matching SHA256; previous contents of that region backed up |
| Automatic warm boot | PASS with the packaged vendor BOOT.BIN; Linux, iiod, SSH and 1 Gbit/s full-duplex Ethernet checked |
| Firmware rollback and reinstall | PASS: previous SD contents restored with matching readback, Linux 6.12.77 booted and legacy RX at 4 MS/s passed for 30 s; candidate reinstalled with matching readback and automatic warm boot |
| Cold boot | PASS: operator-confirmed physical power cycle, automatic SD boot, expected kernel/iiod, gigabit Ethernet and 60-second 24 MS/s checks with both clients |
| Single RX at 24 MS/s, native 1.0 and legacy 0.26 | PASS: 10 minutes per client on the exact image below |
| Client failure recovery and initial final reconnections | PASS for native and legacy clients |
| Post-reinstall native RX without SSH | PASS: 600.004 s at 23.998683 MS/s, no detected DMA overflow |
| Post-reinstall legacy reconnection without SSH | PASS: 60.046 s at 23.994057 MS/s, no detected DMA overflow |
| New SSH sessions during native RX | FAIL: overflow reproduced; increasing iiod priority did not prevent it |
| SSH connected before native RX | PASS: 600.002 s at 23.998782 MS/s with 19 timed diagnostic commands over the existing connection, no detected DMA overflow |
| Independent clean-build reproducibility | PASS: two clean project builds of the tested commit produced identical images using the same Docker builder images on the same VM; second build took 6,572.128 s (1 h 49 min 32 s) |
| Software source collection | PASS: 246 inventory files, all SHA256 values verified for the tested build; runtime/vendor license review pending |
| Firmware inventory and software notices | Firmware-wide review SPDX validated: 757 files, 35 component groups; 14 target source archives, separate Arm corresponding sources and 33 notice texts checked. Vendor redistribution review remains open |
| Image privacy and SSH provisioning | Known-identifier scan passed for the SD image, uncompressed kernel and 1,196 unpacked rootfs entries; no embedded authorized SSH keys or host-key files found. Password-only SSH login with the documented development credentials passed |

## Tested image (2026-09-28)

`build/image.raw`: 135,266,304 bytes (129 MiB), SHA256
`61ce58f1ed89a4d3a1de54080c922821d14c5aafb909afe5186feb4df9e9542b`.
Both clean builds of `f3e6be04aa72dfee4fc1de5f5bd7553bd7767760` produced this hash,
which also matches the earlier staged build. They took 6,631.222 s and
6,572.128 s on the same Linux x86-64 VM with four vCPUs, approximately 8 GiB RAM
and two build jobs. The second build used a new clone and fresh project outputs;
the three Docker builder image identities matched. Rebuilding the builders from
scratch or reproducing on another host has not been tested. Later repository
changes recorded here affect documentation only, not the tested build inputs.

The existing firmware was booted temporarily with SD0 enabled in a RAM-only
device tree. The unmounted test card was identified, backed up over the affected
range, written and read back. An unattended software reboot then loaded the
new image from SD. No saved bootloader environment or QSPI writes were made.
The released-image candidate still disables Linux access to the storage controllers.

The rollback test restored the previous contents of the entire written region,
verified its readback hash, and booted the previous Linux 6.12.77 firmware. Legacy
RX ran at 3.998487 MS/s for 30.027 s without detected DMA overflow. The candidate
was then reinstalled, read back with the hash above, and booted automatically.
Linux 6.12.111, the expected iiod hash, two CPUs, gigabit Ethernet and the normal
storage-disabled profile were checked. This establishes software rollback on
the identified test card, not recovery from a card that cannot boot at all.

After an operator-confirmed physical power cycle, passive UART capture recorded
automatic SD/FIT boot with the expected kernel hash, iiod startup and gigabit
Ethernet. Console checks confirmed the daemon hash and an empty `/root/.ssh`.
Post-cold-boot single-RX checks passed: native 60.001 s at 23.990188 MS/s and
legacy 60.049 s at 23.992743 MS/s, with no detected DMA overflow after the
one-second startup exclusion. Power-off duration was not independently measured.

| Client | Request size | Duration | Measured complex MS/s | DMA overflow after startup |
| --- | --- | --- | --- | --- |
| libiio 1.0 native | 262,144 samples / 1 MiB | 600.001 s | 23.997949 | None detected |
| libiio 0.26 legacy | 2,097,152 samples / 8 MiB | 600.072 s | 23.999011 | None detected |

Both tests used one RX, I16/Q16 and 32 kernel buffers. The first startup second
was excluded from overflow assessment. Initial 60-second checks, recovery from
paused/killed clients and final 60-second reconnections passed for both clients.
These checks measure transport throughput and the DMA overflow indicator; they
do not establish RF sensitivity or sample-by-sample continuity. Four-hour tests
were cancelled in favor of the requested ten-minute scope and are not claimed.

After reinstalling the same image, a 60-second native check detected overflow at
38.21 s while an SSH diagnostic session was active. A subsequent 600-second run
without SSH passed. A controlled 90-second run then reproduced overflow after
the first deliberately scheduled SSH diagnostic session, around 30 s into RX.
The SSH command read kernel/daemon identity, Ethernet state, CPU state and the
storage profile. Repeating the new-connection test with iiod nice priority -10
still produced overflow; the original priority was restored afterward.

With SSH authenticated before RX, the same commands passed first a 90-second
check and then a 600-second check with 19 invocations at 30-second intervals.
The latter explicitly prevented fallback to a new SSH connection. Both used
the original iiod priority. The temporary SSH connection was closed afterward;
no persistent firmware or cryptographic configuration was changed. These
observations implicate new-session setup, but do not isolate its internal cause
or qualify arbitrary concurrent workloads. Complete SSH login before capture.
The failed checks remain part of the qualification record.

Results cover one E200; its physical PCB revision has not been recorded.
TX, dual RX and QSPI programming remain outside the initial release scope.
Raw laboratory logs and device identifiers are kept outside the repository.
