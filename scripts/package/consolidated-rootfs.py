#!/usr/bin/env python3
"""Apply a checked iiod overlay to the qualified Bash CPIO, without extraction.

Run in the pinned Docker package environment. Original archive members remain
byte-for-byte unchanged except the daemon and its defaults; preserve the old
daemon separately. No libiio 0.x ABI files are replaced.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import stat
import struct
import zlib

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    'rootfs.cpio.gz': 'fea1618d00c0c7ee9264d9493b0cebd2e48bbf2e5d9752650812025aa691470c',
    'rootfs.cpio.uboot': '6b5ffcade2bb21ce3aaf170533d19b56fc74d1aeda91628f37665d8c37b4d582',
    'usr/sbin/iiod': '12429fd321481979e8e52c9c8077e6650e87e6128b23ee62900341fe89118c82',
    'usr/lib/libiio.so.1.0.0': 'c6cc085e884469f939bbb80b5b6fb9545d72782eb246b2457a1398bb97c160c9',
    'usr/lib/libzstd.so.1.5.7': '42d24e7e5f54152ef4387fd11d9e70d4445de9ad0c6e71d18957a64f3ce56383',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def entries(data):
    offset, result = 0, {}
    while True:
        start = offset
        if data[offset:offset + 6] != b'070701':
            raise ValueError('Expected newc header')
        fields = [int(data[offset + 6 + n * 8:offset + 14 + n * 8], 16) for n in range(13)]
        offset += 110
        name_bytes = data[offset:offset + fields[11]]
        if not name_bytes or name_bytes[-1] != 0:
            raise ValueError('Invalid member name')
        name = name_bytes[:-1].decode()
        offset = (offset + fields[11] + 3) & ~3
        payload = data[offset:offset + fields[6]]
        if len(payload) != fields[6]:
            raise ValueError('Truncated payload')
        offset = (offset + fields[6] + 3) & ~3
        if name == 'TRAILER!!!':
            if any(data[offset:]):
                raise ValueError('Unexpected archive suffix')
            return result
        key = name[2:] if name.startswith('./') else name
        if key.startswith('/') or '..' in key.split('/') or key in result:
            raise ValueError('Unsafe or duplicate archive member')
        result[key] = (name, fields, payload, data[start:offset])


def member(name, fields, payload):
    name = name.encode() + b'\0'
    fields = fields.copy()
    fields[6], fields[11], fields[12] = len(payload), len(name), 0
    data = b'070701' + b''.join(f'{x:08x}'.encode() for x in fields) + name
    data += bytes((-len(data)) % 4)
    data += payload
    return data + bytes((-len(data)) % 4)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bash-images', type=Path, required=True)
    p.add_argument('--iiod-stage', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build-inputs', type=Path,
                   help='Explicit hashes for a NEW unqualified build; default preserves historical pins')
    a = p.parse_args()
    pins = json.loads(a.build_inputs.read_text()) if a.build_inputs else PINS
    if set(pins) != set(PINS):
        raise ValueError('Build input manifest must identify exactly the five expected inputs')
    inputs = {}
    for name, expected in pins.items():
        source = a.bash_images if name.startswith('rootfs.') else a.iiod_stage
        inputs[name] = (source / name).read_bytes()
        if sha(inputs[name]) != expected:
            raise ValueError(f'Unqualified input {name}')
    original = entries(gzip.decompress(inputs['rootfs.cpio.gz']))
    header = inputs['rootfs.cpio.uboot'][:64]
    if inputs['rootfs.cpio.uboot'][64:] != inputs['rootfs.cpio.gz']:
        raise ValueError('Ramdisk payload mismatch')
    for name in ('usr/sbin/iiod', 'etc/default/iiod'):
        if original[name][1][4] != 1 or not stat.S_ISREG(original[name][1][1]):
            raise ValueError(f'Expected unlinked regular file: {name}')
    replacements = {
        'usr/sbin/iiod': inputs['usr/sbin/iiod'],
        'etc/default/iiod': (ROOT / 'profiles/iq24-consolidated/iiod.default').read_bytes(),
    }
    data = bytearray()
    for key, (name, fields, payload, raw) in original.items():
        data += member(name, fields, replacements[key]) if key in replacements else raw
    inode = max(item[1][0] for item in original.values()) + 1
    epoch = original['usr/sbin/iiod'][1][5]
    added = {}

    def add(name, mode, payload=b''):
        nonlocal inode, data
        if name in original:
            if stat.S_ISDIR(mode) and stat.S_ISDIR(original[name][1][1]):
                return
            raise ValueError(f'Overlay collision: {name}')
        fields = [inode, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, epoch, 0, 0, 0, 0, 0, 0, 0]
        inode += 1
        data += member(name, fields, payload)
        added[name] = dict(mode=oct(mode), sha256=sha(payload), bytes=len(payload))

    for directory in ('opt', 'opt/e200', 'opt/e200/libiio1', 'opt/e200/libiio1/lib'):
        add(directory, stat.S_IFDIR | 0o755)
    add('usr/sbin/iiod-0.26', stat.S_IFREG | 0o755, original['usr/sbin/iiod'][2])
    for name, target in (('libiio.so.1.0.0', 'libiio.so.1'), ('libzstd.so.1.5.7', 'libzstd.so.1')):
        add('opt/e200/libiio1/lib/' + name, stat.S_IFREG | 0o755, inputs['usr/lib/' + name])
        add('opt/e200/libiio1/lib/' + target, stat.S_IFLNK | 0o777, name.encode())
    data += member('TRAILER!!!', [0] * 13, b'')
    data += bytes((-len(data)) % 512)
    result = entries(bytes(data))
    for name in original:
        if name not in replacements and result[name][3] != original[name][3]:
            raise ValueError(f'Unexpected member change: {name}')
    if result['usr/sbin/iiod-0.26'][2] != original['usr/sbin/iiod'][2]:
        raise ValueError('Recovery daemon mismatch')
    compressed = gzip.compress(bytes(data), compresslevel=9, mtime=0)
    words = list(struct.unpack('>7I4B32s', header))
    words[1], words[3], words[6], words[11] = 0, len(compressed), zlib.crc32(compressed), b'E200 SDK14 iiod1 Bash'
    new_header = struct.pack('>7I4B32s', *words)
    words[1] = zlib.crc32(new_header)
    artifacts = {'rootfs.cpio': bytes(data), 'rootfs.cpio.gz': compressed,
                 'rootfs.cpio.uboot': struct.pack('>7I4B32s', *words) + compressed}
    a.output.mkdir(parents=True, exist_ok=False)
    for name, payload in artifacts.items():
        (a.output / name).write_bytes(payload)
    report = dict(status='PACKAGED; BOOT UNTESTED', input_sha256=pins,
                  defaults_sha256=sha(replacements['etc/default/iiod']), added=added,
                  replaced=list(replacements), preserved_original_members=len(original)-len(replacements),
                  artifacts={k: dict(sha256=sha(v), bytes=len(v)) for k, v in artifacts.items()})
    (a.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
