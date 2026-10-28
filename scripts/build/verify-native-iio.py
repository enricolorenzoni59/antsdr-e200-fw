#!/usr/bin/env python3
"""Reject legacy libiio files and ELF dependencies in a native-v1 rootfs."""
import argparse
import json
from pathlib import Path, PurePosixPath
import os
import re
import stat
import subprocess
import tempfile

REQUIRED = ('usr/bin/iio_info', 'usr/bin/iio_rwdev', 'usr/sbin/iiod',
            'usr/lib/libiio.so.1', 'usr/lib/libad9361.so.0')
CONSUMERS = ('usr/bin/iio_info', 'usr/bin/iio_rwdev', 'usr/sbin/iiod',
             'usr/lib/libad9361.so.0')


def resolve(members, name):
    seen = set()
    while True:
        if name in seen or name not in members:
            raise ValueError(f'Missing file or cyclic symlink: {name}')
        seen.add(name)
        mode, payload = members[name]
        if not stat.S_ISLNK(mode):
            if not stat.S_ISREG(mode):
                raise ValueError(f'Expected regular file: {name}')
            return name, payload
        target = payload.decode()
        path = PurePosixPath(target.lstrip('/')) if target.startswith('/') else PurePosixPath(name).parent / target
        parts = []
        for part in path.parts:
            if part == '..':
                if not parts:
                    raise ValueError(f'Symlink escapes rootfs: {name}')
                parts.pop()
            elif part != '.':
                parts.append(part)
        name = '/'.join(parts)


def elf_needed(payload, readelf):
    with tempfile.NamedTemporaryFile() as binary:
        binary.write(payload)
        binary.flush()
        result = subprocess.run([readelf, '-d', '-W', binary.name], check=True,
                                capture_output=True, text=True,
                                env={**os.environ, 'LC_ALL': 'C'})
    if '/opt/e200/libiio1' in result.stdout:
        raise ValueError('Private libiio runtime path remains in ELF dynamic tags')
    return set(re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', result.stdout))


def verify(members, readelf='readelf'):
    for name in members:
        base = PurePosixPath(name).name
        if (base == 'libiio.so.0' or base.startswith('libiio.so.0.') or
                base.startswith('libiio-compat') or
                base in ('iiod-0.26', 'iio_readdev', 'iio_writedev') or
                name == 'opt/e200/libiio1' or name.startswith('opt/e200/libiio1/')):
            raise ValueError(f'Legacy libiio artifact: {name}')
    resolved = {name: resolve(members, name) for name in REQUIRED}
    needed = {}
    for name, (mode, payload) in members.items():
        if stat.S_ISREG(mode) and payload.startswith(b'\x7fELF'):
            needed[name] = elf_needed(payload, readelf)
            if any(dep == 'libiio.so.0' or dep.startswith('libiio.so.0.')
                   for dep in needed[name]):
                raise ValueError(f'ELF still needs libiio v0: {name}')
    for name in CONSUMERS:
        target, _ = resolved[name]
        if 'libiio.so.1' not in needed.get(target, set()):
            raise ValueError(f'Expected native libiio.so.1 dependency: {name}')
    if resolved['usr/lib/libiio.so.1'][0] not in needed:
        raise ValueError('Native libiio library is not an ELF file')
    return {'libiio_abi': 1, 'elf_files_checked': len(needed),
            'native_consumers': list(CONSUMERS)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rootfs', type=Path)
    parser.add_argument('--readelf', default='readelf')
    args = parser.parse_args()
    members = {}
    for path in args.rootfs.rglob('*'):
        mode = path.lstat().st_mode
        payload = os.readlink(path).encode() if stat.S_ISLNK(mode) else path.read_bytes() if stat.S_ISREG(mode) else b''
        members[path.relative_to(args.rootfs).as_posix()] = mode, payload
    print(json.dumps(verify(members, args.readelf), indent=2))
