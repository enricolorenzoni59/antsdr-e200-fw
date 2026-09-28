# License scope

Copyright (c) 2026 ANTSDR E200 firmware project contributors.

Original project code and documentation in this revision are licensed under the
GNU General Public License, version 3 or (at your option) any later version
(`GPL-3.0-or-later`), except where a file or component specifies another license.
The complete GPLv3 text is in [LICENSE](LICENSE).

This includes independently authored build and packaging tools, tests,
applications, and original helper files carrying the project GPL SPDX notice.
The software is provided without warranty, as described in the license.

## Third-party components and patches

This default does not relicense third-party code, patch context, hardware
representations or binaries. Preserve their copyright and license notices.
In particular:

- Linux and patches derived from Linux remain subject to the kernel's applicable
  GPLv2 terms and file-level licenses. They are not converted to GPLv3.
- U-Boot, Buildroot, libiio, iiod and other upstream code retain their respective
  licenses, including file-specific MIT/LGPL notices where present.
- Newly authored GPL-3.0-or-later helpers linked into a modified iiod executable
  impose GPLv3 terms on distribution of that combined executable. Preserve the
  upstream MIT/LGPL notices and supply its complete corresponding source; the
  independently distributed libiio shared library keeps its upstream license.
- Original helper files added by the experimental libiio patch carry explicit
  GPL-3.0-or-later notices. The patch's upstream context retains its own license.
- Vendor BOOT.BIN, FSBL, FPGA artifacts, AMD tools and downloaded dependencies
  are not granted new redistribution permissions by this project's license.

The assembled SD image is a distribution of separately licensed components,
not a single work that can be uniformly relicensed by changing this file.
Corresponding-source and notice requirements apply to the components shipped.
See [the firmware licensing audit](docs/licensing.md) for outstanding checks.

## Earlier versions

This change applies to this revision and subsequent contributions under this
policy. It does not revoke MIT permissions already granted for earlier versions.
Earlier revisions retain the notices in effect when they were distributed.
