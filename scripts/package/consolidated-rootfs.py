#!/usr/bin/env python3
"""Overlay the patched native-v1 daemon and libraries on a native-v1 CPIO.

Require an explicit input manifest: this candidate has no hardware-qualified
historical pins. Reject any leftover libiio v0 ABI, tool or dependency.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import struct
import zlib

ROOT = Path(__file__).resolve().parents[2]
INPUT_NAMES = ('rootfs.cpio.gz', 'rootfs.cpio.uboot', 'usr/sbin/iiod',
               'usr/lib/libiio.so.1.0.0', 'usr/lib/libzstd.so.1.5.7')
spec = importlib.util.spec_from_file_location('native_iio', ROOT / 'scripts/build/verify-native-iio.py')
native_iio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native_iio)


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
    p.add_argument('--build-inputs', type=Path, required=True,
                   help='Explicit hashes for this new, unqualified build')
    a = p.parse_args()
    pins = json.loads(a.build_inputs.read_text())
    if set(pins) != set(INPUT_NAMES):
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
    replacements = {
        name: inputs[name] for name in ('usr/sbin/iiod', 'usr/lib/libiio.so.1.0.0',
                                       'usr/lib/libzstd.so.1.5.7')
    }
    replacements['etc/default/iiod'] = (ROOT / 'profiles/iq24-consolidated/iiod.default').read_bytes()
    for name in replacements:
        if name not in original:
            raise ValueError(f'Missing native rootfs member: {name}')
        if original[name][1][4] != 1 or not stat.S_ISREG(original[name][1][1]):
            raise ValueError(f'Expected unlinked regular file: {name}')
    data = bytearray()
    for key, (name, fields, payload, raw) in original.items():
        data += member(name, fields, replacements[key]) if key in replacements else raw
    data += member('TRAILER!!!', [0] * 13, b'')
    data += bytes((-len(data)) % 512)
    result = entries(bytes(data))
    for name in original:
        if name not in replacements and result[name][3] != original[name][3]:
            raise ValueError(f'Unexpected member change: {name}')
    native_report = native_iio.verify({name: (fields[1], payload)
                                      for name, (_, fields, payload, _) in result.items()})
    compressed = gzip.compress(bytes(data), compresslevel=9, mtime=0)
    words = list(struct.unpack('>7I4B32s', header))
    words[1], words[3], words[6], words[11] = 0, len(compressed), zlib.crc32(compressed), b'E200 native IIO1 Bash'
    new_header = struct.pack('>7I4B32s', *words)
    words[1] = zlib.crc32(new_header)
    artifacts = {'rootfs.cpio': bytes(data), 'rootfs.cpio.gz': compressed,
                 'rootfs.cpio.uboot': struct.pack('>7I4B32s', *words) + compressed}
    a.output.mkdir(parents=True, exist_ok=False)
    for name, payload in artifacts.items():
        (a.output / name).write_bytes(payload)
    report = dict(status='PACKAGED; BOOT UNTESTED', input_sha256=pins,
                  defaults_sha256=sha(replacements['etc/default/iiod']), native_iio=native_report,
                  replaced=list(replacements), preserved_original_members=len(original)-len(replacements),
                  artifacts={k: dict(sha256=sha(v), bytes=len(v)) for k, v in artifacts.items()})
    (a.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
