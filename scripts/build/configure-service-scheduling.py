#!/usr/bin/env python3
"""Wrap the pinned Buildroot service launch commands, preserving their lifecycle."""
import argparse
from pathlib import Path
import stat

LAUNCHES = {
    'S50dropbear': ('ssh', '\tstart-stop-daemon -S -q -p /var/run/dropbear.pid \\\n'),
    'S60iiod': ('iiod', '\tstart-stop-daemon --start --background --make-pidfile \\\n'),
}


def install(target):
    replacements = []
    for name, (policy, original) in LAUNCHES.items():
        path = target / 'etc/init.d' / name
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError(f'Expected regular init script: {path}')
        content = path.read_text()
        wrapped = original.replace('start-stop-daemon',
                                   f'/usr/sbin/e200-service-start {policy} start-stop-daemon', 1)
        if content.count(wrapped) == 1 and original not in content:
            continue
        if content.count(original) != 1 or wrapped in content:
            raise ValueError(f'Unexpected service launch command: {path}')
        replacements.append((path, content.replace(original, wrapped, 1)))
    # Validate both scripts before changing either of them.
    for path, content in replacements:
        path.write_text(content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    install(parser.parse_args().target)
