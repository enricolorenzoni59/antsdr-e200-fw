#!/usr/bin/env python3
"""Prepare review-only SD release assets from one build and its source inventory."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import re
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[2]
MAX_ASSET_BYTES = 2 * 1024**3 - 1


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_identity(tag, commit):
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', tag)
            or '..' in tag or tag.endswith(('.', '.lock'))):
        raise ValueError('Use a new release tag containing letters, digits, dots, underscores or hyphens')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected the full 40-character source commit')


def checked_files(folder, inventory):
    if folder.is_symlink():
        raise ValueError('Source bundle must not contain symlinks')
    actual = set()
    for path in folder.rglob('*'):
        if path.is_symlink():
            raise ValueError('Source bundle must not contain symlinks')
        if path.is_file() and path != folder / 'inventory.json':
            actual.add(path.relative_to(folder).as_posix())
    if not inventory or actual != set(inventory):
        raise ValueError('Source inventory does not cover exactly the collected files')
    for name, expected in inventory.items():
        if digest(folder / name) != expected:
            raise ValueError('Source checksum mismatch: ' + name)


def prepare(work, output, tag, commit):
    validate_identity(tag, commit)
    if output.exists():
        raise ValueError('Release output already exists; use a fresh output directory')
    package = work / 'package'
    sd = json.loads((package / 'sd/manifest.json').read_text())
    image = package / 'sd/e200-sd.img'
    recorded = sd['artifacts']['e200-sd.img']
    if image.stat().st_size != recorded['bytes'] or digest(image) != recorded['sha256']:
        raise ValueError('SD image does not match its build manifest')
    build = json.loads((package / 'build-manifest.json').read_text())
    required = {'scripts/package/release-package.py', 'configs/release.lock.json'}
    if not required <= set(build['source_files']):
        raise ValueError('Build manifest is missing source identities')
    for name, expected in build['source_files'].items():
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT) or digest(source) != expected:
            raise ValueError('Build source does not match this checkout: ' + name)
    sources = package / 'source-materials'
    inventory = json.loads((sources / 'inventory.json').read_text())
    if inventory['project_commit'] != commit:
        raise ValueError('Sources and requested release commit differ')
    checked_files(sources, inventory['files'])
    output.mkdir(parents=True)
    with image.open('rb') as src, lzma.open(output / 'e200-sd.img.xz', 'wb', preset=6) as dst:
        shutil.copyfileobj(src, dst)
    with tarfile.open(output / 'source-materials.tar.gz', 'w:gz') as archive:
        archive.add(sources, arcname='source-materials')
    for source, name in [(package / 'build-manifest.json', 'build-manifest.json'),
                         (package / 'sd/manifest.json', 'sd-manifest.json')]:
        shutil.copy2(source, output / name)
    quick = f'''# E200 quick start — {tag}

Source commit: `{commit}`. Use these steps only for a published release whose
notes identify its exact-image hardware tests and distribution review.

1. Download `e200-sd.img.xz` and `e200-sd.img.xz.sha256` from the same release.
   Verify with `sha256sum -c e200-sd.img.xz.sha256` on Linux, or
   `shasum -a 256 -c e200-sd.img.xz.sha256` on macOS.
2. Write the image to the whole microSD card with an image-writing application
   (decompress to `.img` first if needed). This erases the selected card.
   Keep your original recovery card, insert the new card and boot the E200.
3. Connect Ethernet and configure the PC on the same subnet, for example
   `192.168.1.11/24`. The default board address is `192.168.1.10`;
   SSH uses `root` / `analog`, and the IIO service uses port 30431.

The default credentials and unauthenticated IIO service are for a trusted lab LAN.
Authenticate SSH before a 24 MS/s capture and reuse that connection for light
commands; new SSH connections during RX can cause DMA overflow. TX, dual RX
and QSPI flashing are outside this preview's qualification scope.
'''
    (output / 'QUICKSTART.md').write_text(quick)
    notes = f'''# E200 {tag} — draft review package

Commit: `{commit}`. This exact image has not been hardware-qualified by this
workflow. Historical lab-image results do not qualify this new build.

Hardware tests, cold boot, runtime notices and vendor BOOT.BIN/FSBL/FPGA source
and redistribution review remain to be completed before publication. The
source collection is review material, not distribution clearance. Update these
notes with the exact image hash and completed checks before publishing.

The SD image SHA256 before compression is `{recorded['sha256']}`.
`SHA256SUMS` covers the attached files; `source-materials.tar.gz` includes the
collected source/configuration/notices inventory. QSPI byproducts are excluded.
See `QUICKSTART.md` for the install flow after this draft is ready for publication.
'''
    (output / 'RELEASE.md').write_text(notes)
    status = {'tag': tag, 'source_commit': commit, 'status': 'DRAFT; REVIEW REQUIRED',
              'hardware_validated': False, 'redistribution_review_complete': False,
              'image': recorded, 'source_inventory_sha256': digest(sources / 'inventory.json')}
    (output / 'release-manifest.json').write_text(json.dumps(status, indent=2) + '\n')
    checksum = digest(output / 'e200-sd.img.xz') + '  e200-sd.img.xz\n'
    (output / 'e200-sd.img.xz.sha256').write_text(checksum)
    assets = sorted(output.iterdir())
    if any(path.stat().st_size > MAX_ASSET_BYTES for path in assets):
        raise ValueError('A release asset exceeds the GitHub limit; split the source bundle before retrying')
    (output / 'SHA256SUMS').write_text(''.join(f'{digest(path)}  {path.name}\n' for path in assets))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    prepare(args.work.resolve(), args.output.resolve(), args.tag, args.commit)
