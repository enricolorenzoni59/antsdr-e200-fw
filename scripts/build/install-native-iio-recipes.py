#!/usr/bin/env python3
"""Install the pinned E200 native-IIO recipes in a fresh Buildroot workspace."""
import argparse
import hashlib
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
# Git blob identity from the pinned ADI Buildroot tree. This v0-only patch
# cannot be carried onto v1's rewritten Python bindings, even when disabled.
OBSOLETE_PATCHES = {'0001-bindings-python-fix-library-loading.patch':
                    'f8715b4c5b714abc3a8c021c5a648562dbce825e'}


def install(buildroot, external):
    recipes = ROOT / 'profiles/native-iio/recipes'
    targets = [(tree / 'package' / package, package)
               for tree, package in ((buildroot, 'libiio'), (external, 'libad9361-iio'))]
    obsolete = []
    for target, package in targets:
        # Preserve upstream Kconfig/init files. Refuse an unexpected tree layout.
        if not (target / 'Config.in').is_file():
            raise ValueError(f'Missing upstream package: {target}')
        for patch in target.glob('*.patch'):
            data = patch.read_bytes()
            blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
            if package != 'libiio' or OBSOLETE_PATCHES.get(patch.name) != blob:
                raise ValueError(f'Unexpected upstream package patch: {patch}')
            obsolete.append(patch)
    for patch in obsolete:
        patch.unlink()
    for target, package in targets:
        for suffix in ('.mk', '.hash'):
            shutil.copy2(recipes / (package + suffix), target / (package + suffix))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('buildroot', type=Path)
    parser.add_argument('external', type=Path)
    args = parser.parse_args()
    install(args.buildroot, args.external)
