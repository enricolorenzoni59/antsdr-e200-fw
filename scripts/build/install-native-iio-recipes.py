#!/usr/bin/env python3
"""Install the pinned E200 native-IIO recipes in a fresh Buildroot workspace."""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]


def install(buildroot, external):
    recipes = ROOT / 'profiles/native-iio/recipes'
    for tree, package in ((buildroot, 'libiio'), (external, 'libad9361-iio')):
        target = tree / 'package' / package
        # Preserve upstream Kconfig/init files. Refuse an unexpected tree layout.
        if not (target / 'Config.in').is_file():
            raise ValueError(f'Missing upstream package: {target}')
        for suffix in ('.mk', '.hash'):
            shutil.copy2(recipes / (package + suffix), target / (package + suffix))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('buildroot', type=Path)
    parser.add_argument('external', type=Path)
    args = parser.parse_args()
    install(args.buildroot, args.external)
