# SSH connection-phase investigation, 2026-10-27

Changing key exchange, authentication or Dropbear's small-code optimization did
not establish a fix for new SSH connections during 24 MS/s RX. Overflow was
reproduced before authentication completed, as well as with public-key login and
only the command `true`. Password hashing and heavy diagnostic commands are
therefore not required to trigger the problem.

This follows the [scheduler and DMA investigation](ssh-rx-investigation-2026-10-27.md).
The E200 continued running the original native-libiio 1.0 image from `8c9e790`,
SD-image SHA256 `4c6ec10df862d81f802bcaf9b79f4347a7f7e525c52576adc5808c72dfabf5de`.
No kernel, SD, QSPI or persistent boot configuration was changed in this phase.

## Protocol and build observations

The installed daemon is Dropbear 2026.94. The Mac client negotiated:

- Key exchange: `mlkem768x25519-sha256`.
- Host signature: `ssh-ed25519`.
- Session cipher: `chacha20-poly1305@openssh.com`.
- Compression: none.

The actual Buildroot configuration selected `BR2_PACKAGE_DROPBEAR_SMALL=y`.
The compiled source had `DROPBEAR_SMALL_CODE=1` and no local override. Reverse
DNS was disabled. The kernel already had `CONFIG_PREEMPT=y`; `CONFIG_FTRACE`
was disabled, so kernel latency tracing was unavailable in this image.

## Method

A single native network RX client used I16/Q16, 262,144 complex samples per
request (1 MiB), and 32 buffers. A pass requires measured throughput of at least
99% of the configured rate and no sticky DMA overflow after the first startup
second. Overflow is polled approximately once per second; reported times are
first observations, not exact interrupt timestamps. These checks do not prove
sample continuity or RF performance.

Standard 60-second connection tests scheduled three fresh connections at 15, 30 and
45 seconds. The 120-second tests scheduled ten, every ten seconds from 15 to
105 seconds. All connections explicitly disabled SSH multiplexing; an existing
master was used only for setup and cleanup outside RX. No second RX consumer
or unrelated board diagnostics ran during a capture.

The TCP control read the server identification and closed. The version-only
control additionally sent a client identification string and closed after a
bounded wait, without sending a client KEXINIT. The handshake-only control used
`PreferredAuthentications=none`, `PubkeyAuthentication=no` and `BatchMode=yes`;
it verified that the server advertised authentication methods and SSH exited
255 as expected. It did not authenticate or open a shell/channel.

Successful logins used either the existing development password or a temporary
Ed25519 key restricted to `true` with forwarding and PTY disabled. Agent access
was disabled and only the test identity was offered. Curve25519 comparisons
explicitly selected `KexAlgorithms=curve25519-sha256` and the debug transcript
verified the negotiated algorithms. Successful `true` tests used no PTY.
Those tests include connection teardown;
they do not attribute the overflow to cryptographic computation alone.

Further lifecycle controls kept three password prompts open, without submitting
credentials, until RX had ended. Authenticated no-channel controls likewise
kept connections open. Separate close tests opened at 15 s and explicitly closed
at 35 s while RX continued. A preauthenticated PTY running `sleep` was used for
rekey comparisons: three newline-only controls were compared with three OpenSSH
`~R` requests. Debug logs verified each additional received NEWKEYS message.
See the [OpenSSH escape documentation](https://man.openbsd.org/ssh#ESCAPE_CHARACTERS).
Both default and Curve25519 key exchange were tested. New-master controls
created a separate authenticated master for each diagnostic command using
`ControlPersist=600`, checked that all remained alive after RX, and closed them
only after the receiver had exited. These short controls measure only their
stated workload and duration. The ten-minute rate test scheduled 29 ordinary
password logins with light diagnostics, every 20 seconds from 20 through 580 s.
The diagnostics read kernel/daemon identity, link, CPU and storage state; they
did not launch the Python scheduling query used in the previous investigation.

| Trial | RX seconds | Connections/events | Effective MS/s | Result / first observed overflow |
| --- | ---: | ---: | ---: | --- |
| No new connection | 60.008 | 0 | 23.991546 | PASS |
| TCP identification read only | 60.003 | 3 | 23.989425 | PASS |
| Client/server version strings only | 120.002 | 10 | 23.994543 | PASS |
| Default handshake, no authentication | 60.008 | 3 | 23.983018 | PASS |
| Default handshake, no authentication, repeated | 120.010 | 10 | 23.988523 | FAIL; 16.064 s |
| Curve25519 handshake, no authentication | 60.009 | 3 | 23.978059 | FAIL; 16.118 s |
| Password + true, default KEX | 60.003 | 3 | 23.985131 | FAIL; 16.112 s |
| Password + true, Curve25519 | 60.016 | 3 | 23.949231 | FAIL; 16.107 s |
| Public key + true, default KEX | 60.008 | 3 | 23.908728 | FAIL; 16.085 s |
| Public key + true, Curve25519 | 60.008 | 3 | 23.891116 | FAIL; 16.090 s |
| Password, no channel, then close | 60.001 | 3 | 23.964081 | FAIL; 16.099 s |
| Optimized daemon: password + true | 60.007 | 3 | 23.970410 | FAIL; 16.096 s |
| Optimized daemon: public key + true | 60.004 | 3 | 23.927846 | FAIL; 16.098 s |
| Three password prompts held open | 60.000 | 3 | 23.990394 | PASS |
| Existing PTY, newline controls | 60.010 | 3 | 23.986574 | PASS |
| Existing connection, default rekey | 60.004 | 3 | 23.988942 | PASS |
| Existing connection, Curve25519 rekey | 60.009 | 3 | 23.991404 | PASS |
| Password prompt opened at 15 s, closed at 35 s | 60.004 | 1 | 23.984662 | FAIL; 16.091 s |
| Three new authenticated connections held open | 60.000 | 3 | 23.990345 | PASS |
| Authenticated connection opened at 15 s, closed at 35 s | 60.000 | 1 | 23.977292 | FAIL; 16.085 s |
| New persistent masters + light diagnostics | 60.007 | 3 | 23.930855 | FAIL; 16.087 s |
| 20 MS/s, password + light diagnostics | 60.001 | 3 | 19.992621 | PASS |
| 22 MS/s, password + light diagnostics | 60.009 | 3 | 21.990739 | PASS |
| 23 MS/s, password + light diagnostics | 60.003 | 3 | 22.967013 | FAIL; 16.063 s |
| 22 MS/s, password + light diagnostics, extended | 600.009 | 29 | 21.998349 | FAIL; 460.823 s |

## Temporary optimized daemon

A separate copy of the original Dropbear build was compiled on the VM with
`DROPBEAR_SMALL_CODE=0`, retaining the compiler and configure options and bundled
crypto libraries. Only the daemon program was linked, whereas the original
binary also contains other Dropbear programs. This was a package-only experiment,
not a full firmware rebuild. Compilation completed successfully in 28.841 seconds;
the original build directory was read-only and remained unchanged.

The experimental ARM binary SHA256 was
`993a32e347d41c960ef4765d59d9ee23ec58c7699313973f370c29b56de01c08`.
It ran from RAM on a separate port, with the same existing Ed25519 host key,
ordinary scheduling and no replacement of the normal SSH daemon. It logged to
a RAM file, while the original service uses its normal logging configuration;
this comparison does not isolate logging or program selection as independent
variables. Nevertheless, both password and public-key RX tests failed, so this
build was rejected as a fix.

After testing, its process and binary were removed. The temporary authorized
key was removed only after verifying its exact content hash; the previous
absence of an authorized-keys file was restored. No private key entered the
firmware or public repository. The original daemon and iiod hashes remained:

- Dropbear: `108651ceb7241379f6ae7a1c22d0ecec519bb44e4dbbd09f03a149dc4ec8932e`.
- iiod: `12429fd321481979e8e52c9c8077e6650e87e6128b23ee62900341fe89118c82`.

## Interpretation and remaining work

The short default-handshake pass is not evidence of reliability: the same class
of short successes occurred in the preceding scheduler experiments. A failure
with authentication disabled means password hashing, public-key verification
and shell startup are not necessary causes. It does not establish that the
cryptographic computation alone is responsible; negotiation also involves
packet handling, process execution and shared kernel resources.

Reducing the rate did not establish a reliable workaround. At 20 and 22 MS/s,
three light diagnostic logins passed a 60-second test. At 23 MS/s the same test
failed. The extended 22 MS/s capture then failed: 600.009230 s at 21.998349 MS/s,
29 successful logins, with the first overflow observed at 460.823 s. A high
average throughput does not compensate for overflow. The 20 MS/s short pass
was not extended and does not qualify long-running concurrent SSH. All rate
comparisons here use the native client; they do not qualify legacy clients.

The lifecycle controls also rule out teardown as a necessary trigger. A new
connection left at its password prompt produced overflow at 16.091 s despite
not being closed until about 35 s. An authenticated no-channel connection
likewise produced overflow at 16.085 s, before its scheduled 35 s close. The
parent and receiver clocks have a small startup offset; the approximately
19-second separation makes this ordering unambiguous. No password was submitted
in the first test. Other held-connection controls passed briefly, demonstrating
why such short successes are insufficient. Forced rekeys passed only their
three-event, 60-second comparisons; this does not qualify arbitrary rekey loads.

The minimal failing workload observed was a new connection reaching
negotiation/authentication-method selection. It does not isolate a particular
cryptographic algorithm, kernel function or hardware stall. Changing SSH
algorithms, selecting public-key authentication, lowering the rate to 22 MS/s
or merely delaying disconnects is not a demonstrated fix. In particular, three
fresh persistent masters kept alive through the entire 60-second capture still
failed, with overflow first observed at 16.087 s. All three masters were checked
alive after RX and only then closed. Establishing a master during capture is
therefore not equivalent to establishing it before capture.

At 24 MS/s, the validated operational procedure remains to authenticate SSH
before capture and [reuse the existing connection](clients.md) for the measured
light commands. A root-cause fix still needs correlated measurements of DMA
completion/requeue latency, scheduler/IRQ latency and TCP completion stalls.
A diagnostic kernel with tracing would be a separate experiment; enabling
preemption alone is not a new option because it is already enabled.

## Final board state

The final single-RX self-test (`e200-selftest --json --rx-channels 1 --seconds 5`)
passed all 22 checks. A default two-RX self-test had rejected missing RX2
channels; its request did not match the active single-RX profile. A final
60.003345-second native capture at 24 MS/s without new SSH passed at
23.989208 MS/s, without detected DMA overflow. This also restored the configured
sample rate to 24 MS/s after the rate comparisons.

The gigabit full-duplex link had zero reported Ethernet errors or drops.
Original daemon/library hashes, disabled SD/QSPI nodes, absence of the temporary
key/binary, normal SSH/IIO listener ports and closure of all experimental
masters were verified. No source or runtime default was changed by these tests.

Raw receiver JSON, SSH debug transcripts, event timings and build evidence are
retained locally under `work/qualification/ssh-handshake/`. Aborted host-side
probe attempts are explicitly marked invalid/incomplete and excluded from the
results table. No physical cold boot, TX or dual-RX qualification was performed.
