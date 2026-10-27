# SSH during RX investigation, 2026-10-27

The tested nice, CPU-affinity and scheduler changes did **not** eliminate
fresh-SSH DMA overflow reliably at 24 MS/s. Several short tests passed and then
failed on repetition or longer runs. The 4 MiB DMA experiment also failed its
baseline throughput check. Both code candidates were reverted.

## Method and baseline

The baseline was the native-libiio image built from `8c9e790`, SHA256
`4c6ec10df862d81f802bcaf9b79f4347a7f7e525c52576adc5808c72dfabf5de`.
It previously passed ten-minute single-RX captures with each client, without
opening new SSH connections; see the [original validation record](native-iio-validation-2026-10-27.md).

Tests used one RX, I16/Q16, 24 MS/s and a standard network client on the receiving
Mac. Baseline native requests were 262,144 complex samples (1 MiB), with 32
blocks. Legacy requests were 2,097,152 samples (8 MiB), with 32 kernel buffers.
A pass requires at least 99% measured throughput and no sticky DMA overflow
after excluding the first startup second. This does not verify sample continuity
or RF performance.

Each fresh login opened a separate TCP connection, authenticated, read the kernel
version, iiod hash, link/storage state and Python scheduling metadata, then
closed. Ordinary 90-second tests opened three connections at 20, 40 and 60 s;
180-second stress tests opened 15, every ten seconds from 20 through 160 s.
Extended tests scheduled 19 connections over 600 s and were stopped early once
failure was established. Failed runs and partial-run logs were preserved.

## Scheduling results

Normal iiod and Dropbear use `SCHED_OTHER`, nice 0. Native workers place DMA work
on CPU 0 and network writers on CPU 1; the Ethernet IRQ is normally on CPU 0.
Changing the Dropbear listener changes the inherited scheduling of new sessions.
All-thread iiod trials explicitly changed every existing TID, including the
network listener, so newly created workers inherited the policy. An active
snapshot verified nine iiod threads at `SCHED_RR` priority 10.

| Change from baseline | Short result | Longer/repeated result |
| --- | --- | --- |
| None, native | FAIL, 23.738520 MS/s; overflow at 21.121 s | First login started at 20 s |
| Dropbear nice 19, both CPUs | FAIL, 23.854146 MS/s | Overflow at 21.113 s |
| Dropbear nice 19, CPU 1 | FAIL, 23.889817 MS/s | Overflow at 22.111 s |
| Dropbear nice 19, CPU 0 | PASS, 90 s, 23.992788 MS/s | FAIL; overflow visible by 40 s in the extended run |
| Dropbear nice 0, CPU 0 | FAIL, 23.773358 MS/s | Overflow at 22.135 s |
| Dropbear `SCHED_IDLE`, nice 19, CPU 0 | PASS, 90 s, 23.993689 MS/s | FAIL with 15 logins; overflow at 76.447 s |
| All iiod threads nice −10; Dropbear `SCHED_IDLE` on CPU 0 | PASS, 180 s/15 logins, 23.996846 MS/s | FAIL; overflow visible by 250 s in the extended run |
| All iiod threads nice −10; ordinary SSH | FAIL | Overflow visible by 25 s; stopped early |
| Ethernet IRQ on CPU 1; iiod nice −10; SSH `SCHED_IDLE` on CPU 1 | FAIL, 20.331962 MS/s | Overflow at 2.011 s, before SSH; rejected for baseline capacity loss |
| All iiod threads `SCHED_RR` priority 10; ordinary SSH | PASS, 90 s/3 logins, 23.994494 MS/s | FAIL; overflow visible by 50 s in the extended run |
| None, legacy client | FAIL, 180 s/15 logins, 23.405552 MS/s | Overflow at 20.943 s |

A larger positive nice value reduces priority. `SCHED_IDLE` is a separate class
below ordinary nice 19; nice does not affect scheduling within that class.
The kernel treats nice as a per-thread property. These distinctions informed
the trials, but did not establish a reliable fix. See the Linux
[nice API](https://man7.org/linux/man-pages/man2/setpriority.2.html) and
[scheduling policy manual](https://man7.org/linux/man-pages/man7/sched.7.html).

No realtime throttling parameter was changed. Realtime trials had a separate,
time-bounded watchdog that restored the original configuration. All temporary
scheduler, affinity and IRQ changes were removed.

## Rejected 4 MiB candidate

Commits `3ca9b23` and `c22d5b2` raised the cached RX allocation limit and transport
payload ceiling to 4 MiB, used 32 transport slots within the existing 128 MiB
bound, and selected 4 MiB legacy DMA blocks. The hypothesis was to give DMA
handoff more time. The results did not validate that hypothesis as a solution.

The isolated VM build used fresh kernel output and a freshly compiled IIO stack,
with verified Bash rootfs and vendor inputs reused from the baseline. It took
689.181 s. Kernel source comparison identified only the DMA-buffer source file
as changed; source code shared with the previous build was mounted read-only.
The old source was checked unchanged afterward. Transport sanitizers, ownership,
layout, ABI and package checks passed, as did CI on `c22d5b2`.

The candidate image was 135,266,304 bytes, SHA256
`dd2c7b04fa7ead1e7b3860b8ce532ef2a050f1a08104bc6b3f2cb2bc51619af5`.
Its zImage SHA256 was
`6601c6aadb42dc6fca2f907fce69c81cfa58ce3d6dc48c9988fc7a52110ed3f7`.
The original SD range was backed up on the Mac and VM. Candidate write/readback
passed, automatic boot succeeded, and all 22 local self-tests plus the ARM
libad9361 read test passed. Native libiio remained 1.0.0 throughout.

| Native 4 MiB requests | Result |
| --- | --- |
| 4 MS/s, 32 blocks | First dequeue timed out with the client's 5 s context timeout |
| 4 MS/s, 2 blocks | Data transferred without detected overflow; 3.957395 MS/s over 5.034 s narrowly missed the 99% criterion |
| 24 MS/s, 32 blocks, SSH connected beforehand | FAIL, 23.294666 MS/s over 90.027 s; overflow at 3.050 s, before the first timed diagnostic |
| 24 MS/s, 8 blocks, fresh SSH | FAIL, 23.032336 MS/s over 90.051 s; overflow at 4.097 s, before the first login |

The eight-block test kept the original total DMA payload capacity of 32 MiB;
it also failed. Requests for 48 or 64 one-MiB blocks on the original ARM build
were rejected with `EINVAL` before streaming. They were not treated as a usable
buffering workaround.

## Restored state and limits

The original 129 MiB SD range was restored and read back after dropping the
page cache; SHA256 again matched the baseline image above. Automatic warm boot
loaded the original kernel (`7bf4fa5935f6da26072f803fa0f4063d8fef7e78f7205fd1bb3e15cee57f38ad`)
and original iiod/library hashes. The two SD controllers and QSPI returned to
the normal disabled Linux profile. iiod and Dropbear are back at `SCHED_OTHER`,
nice 0, with the original affinity and Ethernet IRQ settings.

All 22 self-tests passed after restoration. Subsequent 60-second 24 MS/s captures
passed without detected DMA overflow: native 23.989857 MS/s and legacy
23.989405 MS/s. FPGA, native libiio 1.0 and the gigabit full-duplex link were verified.

A final native capture on the restored image passed 600.000186 s at
23.998402 MS/s, with 19 successful diagnostic commands over a connection
authenticated before RX and no detected DMA overflow after startup. Requests
were 1 MiB with 32 blocks. These commands read kernel/daemon identity, link,
CPU and storage state; they excluded the Python scheduling query used in the
scheduling matrix. Fresh-login failures were also observed with light diagnostics
in the original validation, but these trials do not isolate handshake cost as
the sole cause. The client prevented fallback to a fresh TCP connection. See
the [persistent-connection recipe](clients.md). This qualifies the measured
light workload, not arbitrary shell commands.

The previous FIT is retained locally for recovery. A 320 KiB XMODEM transfer to
bootloader RAM at 115200 baud passed CRC32 with zero retries and exercised block
number wrap. The complete FIT was not transferred by UART; the 921600 baud trial
failed and was returned to 115200. This bootloader has no TFTP command. No QSPI
write or saved bootloader-environment change occurred. Physical cold boot was
not tested in this investigation.

The rejected scheduler and 4 MiB defaults were reverted in Git. Raw UART,
receiver JSON, per-login timings, backups and build manifests remain under
`work/qualification/ssh-scheduling/` and `work/qualification/ssh-4m/` locally;
device identifiers and host keys are omitted from this public report.

The remaining operational rule is to establish SSH before a 24 MS/s capture and
keep concurrent work within the previously measured scope. The tests do not
identify a single root cause. A further fix needs measurements of DMA/IRQ latency
and transport stalls during authentication, rather than another unverified
priority preset. TX, dual RX and arbitrary shell workloads remain unqualified.
