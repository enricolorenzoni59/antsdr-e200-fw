# Contributing

Keep this repository focused on the default `./build.sh` microSD build. Include
only dependencies, packaging/source-distribution tools, relevant tests and user
documentation. Keep laboratory logs, captures and unrelated experiments out.

Run `python3 -m pytest tests/host -q`.
Linux CI additionally prepares the pinned iiod source and runs transport
sanitizers, RX layout checks and pipeline tests. Boot/DMA changes need hardware
evidence; host tests do not qualify an image on the E200.

Original project contributions use GPL-3.0-or-later. Preserve third-party
licenses, source pins and attribution as described in [LICENSING.md](LICENSING.md).
Propose generic changes to the relevant upstream project where possible.
