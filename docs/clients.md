# IIO clients

Connect the E200 to a trusted Gigabit receiver LAN. The development address is
192.168.1.10/24; IIO has no authentication. Use one receiver application at a time.

The firmware uses native libiio 1.0.0 for all local tools, the daemon and
libad9361. It contains no libiio 0.x library or ABI shim. Local programs linked
against `libiio.so.0` must be ported and rebuilt before installing them.

The daemon still serves native libiio 1.0 and legacy 0.26 **network clients**;
this protocol compatibility does not require an old library on the E200.
Build/install the
host library and utilities using the matching
[ADI instructions](https://github.com/analogdevicesinc/libiio). Host libraries
must match the receiving computer; the ARM libraries inside the firmware cannot
be loaded on an x86-64 or macOS host.

The native-IIO image passed ten-minute single-RX I16/Q16 captures at 24 MS/s
with each client using 32 buffers and these request sizes:

| Client | Complex samples per request | Request bytes |
| --- | --- | --- |
| Native libiio 1.0 | 262144 | 1 MiB |
| Legacy libiio 0.26 | 2097152 | 8 MiB |

Legacy 1 MiB requests overflowed at this rate in laboratory tests. Applications
that cannot choose these sizes may require a lower sample rate. Record the
application/library version, request size, achieved throughput and DMA overflow
status; elapsed time alone is not a pass. These results do not establish TX,
dual-RX or RF sensitivity performance.

The board self-test now uses `iio_rwdev -u local:` for bounded receive checks.
The old `iio_readdev` and `iio_writedev` commands are not installed.

Complete SSH login before starting a 24 MS/s capture. Opening new SSH sessions
during native RX reproduced DMA overflow. A connection established beforehand
passed a 90-second native RX comparison with two timed diagnostic commands.
Heavy commands and arbitrary mixed workloads remain unqualified. See
[the native-image qualification record](native-iio-validation-2026-10-27.md)
for the exact image and results. The older mixed-runtime image also passed a
separate ten-minute test with 19 diagnostic commands, recorded in
[historical results](release-status.md).
