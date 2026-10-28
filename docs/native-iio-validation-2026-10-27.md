# Native libiio firmware validation, 2026-10-27

The native-IIO image was built from commit
`8c9e7901c2587b5933db4ad55ce50bc5399402ef`, installed on the laboratory E200
microSD and booted automatically. This record distinguishes completed checks
from checks requiring a physical operator; it does not qualify TX, dual RX or RF sensitivity.

## Image and build

| Item | Recorded result |
| --- | --- |
| Complete ARM build | PASS, 7,553.728 seconds (2 h 5 min 54 s), fresh project output directories |
| Image size | 135,266,304 bytes (129 MiB) |
| Image SHA256 | `4c6ec10df862d81f802bcaf9b79f4347a7f7e525c52576adc5808c72dfabf5de` |
| Kernel | Linux 6.12.111, GCC 15; zImage SHA256 `7bf4fa5935f6da26072f803fa0f4063d8fef7e78f7205fd1bb3e15cee57f38ad`, identical to the previous image |
| Rootfs | Buildroot 2026.08, Arm GNU 14.2, BusyBox and Bash |
| Native IIO source | libiio v1.0.0, `9a929664fd3effa500430626803ac59ecf2f4ed3` |
| Native libad9361 source | `7d8e7cadd07636cafb7a87d6bcdcc4dd4fcca9b3` |
| Firmware ABI scans | PASS: 99 ELF files in baseline rootfs, 106 in Bash/final rootfs |
| Native transport checks | PASS: sanitizers, ownership/cancellation, readline/event waits, 104 layout cases and pipeline checks |
| Rootfs/package checks | PASS: QEMU ARM BusyBox/Python, Bash smoke check, ext4/CPIO integrity, input hashes, FIT checksums, FAT readback and image structure |

The first build attempt stopped because Ubuntu's live archive had removed the
pinned CA bootstrap package. Commit `8c9e790` fetches the same package from the
same dated Ubuntu snapshot used by APT. Its original SHA256 was verified and
preserved. The complete successful build includes this fix.

The existing VM's selected historical intermediate build directories were
removed after checking recovery images; source trees, images, logs, download
caches and source/license materials were preserved. The valid existing 8 GiB
swap file was activated because available RAM varied with VM ballooning.
It was returned to its original inactive state after the build and ARM helper
compilation. No persistent swap configuration was added.

## Installation and runtime

The previous firmware was first measured at 24 MS/s for 60 seconds with each
client: native 23.99158 MS/s and legacy 23.99343 MS/s, without detected DMA
overflow after the one-second startup exclusion.

UART access and the working boot path were verified before reboot. U-Boot
loaded and verified the existing SD FIT, then only the SD0 status property was
changed in its RAM copy of the device tree. The old firmware booted with SD0
available and unmounted; QSPI and SD1 stayed disabled.

The first 129 MiB of the identified card were backed up to the Mac and VM.
The backup matched the previous image SHA256
`61ce58f1ed89a4d3a1de54080c922821d14c5aafb909afe5186feb4df9e9542b`.
This is a backup of the affected range, not a full-card backup. The new image
was staged in RAM, hash checked, written to that unmounted card, flushed and
read back after dropping the kernel page cache. The readback matched the new
image hash above. No QSPI write or saved bootloader-environment change occurred.

The first automatic SD boot reached Linux, SSH and iiod. The runtime checks
confirmed:

- `iio_info` and `iio_rwdev` report libiio 1.0.0 with local/network/XML backends.
- iiod maps `/usr/lib/libiio.so.1.0.0`; the private library path is absent.
- No `libiio.so.0`, `iiod-0.26` or old `iio_readdev` executable remains.
- Both SD controllers and QSPI return to the normal disabled Linux profile.
- Ethernet reports 1,000 Mb/s, full duplex, with carrier.
- All 22 local single-RX self-test checks pass, including a bounded 4 MS/s
  receive through the new `iio_rwdev` utility.
- An ARM program built with the new SDK successfully reads FIR enable through
  libad9361 and sampling frequency through native libiio attributes. This tests
  the actual hardware/library path; it does not exercise every libad9361 API.

The libad9361 library retains its own `libad9361.so.0` name and 0.4 version.
Its dependency is `libiio.so.1`; its own SONAME does not indicate a legacy
libiio dependency. Legacy 0.26 libraries are used only on the receiving Mac
to test network protocol compatibility.

## Reception and recovery

| Client | Duration | Measured complex MS/s | DMA overflow after startup |
| --- | --- | --- | --- |
| Native libiio 1.0 | 600.007 s | 23.998560 | None detected |
| Legacy libiio 0.26 | 600.075 s | 23.998885 | None detected |

Both clients passed initial capture, reconnect, recovery after a three-second
paused consumer, and recovery after a killed consumer. The deliberate pause
caused overflow and the deliberate kill terminated the client, as expected;
the subsequent captures passed. There are six recorded case outcomes per client.

A controlled 90-second native test opened a **new SSH connection** at 30.107 s.
DMA overflow was first detected at 31.160 s; the capture failed the overflow
criterion despite averaging 23.979725 MS/s. This reproduces the pre-existing
limitation. A second 90-second test ran two diagnostic commands over an SSH
connection established before RX, at 30 and 60 s. It passed at 23.993848 MS/s
without detected DMA overflow. Complete SSH login before capture; these checks
do not qualify arbitrary concurrent workloads.

A second automatic warm reboot also reached Linux, iiod and SSH, with verified
runtime hashes, native CLI versions, working FPGA and gigabit full-duplex link.
Both SD controllers and QSPI remained disabled. The ARM libad9361 read test
passed again after this reboot. Subsequent 60-second 24 MS/s captures passed
with both clients: native 23.983259 MS/s and legacy 23.993368 MS/s,
with no detected DMA overflow after startup.

Final telemetry showed 40.351 °C at the AD9361 and 49.093 °C at the XADC,
with a gigabit full-duplex link and zero Ethernet error/drop counters at that
snapshot. The board clock is not synchronized; host timings identify this run.

Physical cold-boot qualification requires an operator power cycle and is not
claimed for this image. The previous image's cold-boot and rollback results
remain historical evidence in [release status](release-status.md).

RX uses one receiver, I16/Q16 and 32 buffers. Native requests are 262,144 complex
samples (1 MiB); legacy requests are 2,097,152 samples (8 MiB). The test checks
measured throughput and the sticky DMA overflow flag, excluding the first
startup second. It does not verify sample-by-sample continuity or RF performance.

Raw UART transcripts, image backups, helper sources and JSON results are retained
locally under `work/qualification/native-v1/`; device identifiers and host keys
are not included in this public record. The VM build directory preserves the
full build log and input/output manifests.
