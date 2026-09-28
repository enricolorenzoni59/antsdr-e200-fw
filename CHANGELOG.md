# Changelog

## Unreleased

- Default to `./build.sh` and publish the verified microSD image as `build/image.raw`.
- Remove laboratory archives, alternate build entry points and unrelated experiments.

- License original project code and documentation under GPL-3.0-or-later.
  Preserve third-party licenses and permissions already granted for earlier
  MIT versions; document the scope in `LICENSING.md`.

## v0.1.0-dev.1 — public developer preview

- Publish the standalone E200 firmware source tree with component pins and provenance.
- Add a public-source SD build pipeline, structural packaging checks and manifests.
- Use the verified official v0.39 BOOT.BIN in the public build; historical lab
  BOOT.BIN qualification is not inherited.
- Run Python regressions, native transport/lifetime sanitizers, RX layout guards
  and zero-copy pipeline checks in GitHub Actions.
- Provide separately installed, unpatched libiio 0.26 and 1.0 host clients.
- Preserve selected historical reports and an index of omitted raw evidence.
- Keep six focused MicroPhase PRs separate from this distribution.

No qualified binary release is included. Exact-image SD cold boot, recovery,
long-run reception and binary licensing materials remain tracked in
[release status](docs/release-status.md).
