# IIO clients

Connect the E200 to a trusted Gigabit receiver LAN. The development address is
192.168.1.10/24; IIO has no authentication. Use one receiver application at a time.

The firmware serves native libiio 1.0 and legacy 0.26 clients. Build/install the
host library and utilities using the matching
[ADI instructions](https://github.com/analogdevicesinc/libiio). Host libraries
must match the receiving computer; the ARM libraries inside the firmware cannot
be loaded on an x86-64 or macOS host.

For the tested single-RX I16/Q16 configuration at 24 MS/s, use 32 kernel buffers:

| Client | Complex samples per request | Request bytes |
| --- | --- | --- |
| Native libiio 1.0 | 262144 | 1 MiB |
| Legacy libiio 0.26 | 2097152 | 8 MiB |

Legacy 1 MiB requests overflowed at this rate in laboratory tests. Applications
that cannot choose these sizes may require a lower sample rate. Record the
application/library version, request size, achieved throughput and DMA overflow
status; elapsed time alone is not a pass. These settings do not qualify the
newly built image or establish TX, dual-RX or RF sensitivity performance.

Complete SSH login before starting a 24 MS/s capture. Opening new SSH sessions
during native RX reproduced DMA overflow. A connection established beforehand
passed a ten-minute native RX test with 19 timed diagnostic commands; this does
not qualify heavy commands or arbitrary mixed workloads. See
[the qualification record](release-status.md) for the exact image and results.
