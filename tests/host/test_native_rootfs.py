"""Exercise native rootfs overlay, integrity and preservation before output."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import struct
import sys
import zlib

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('overlay', ROOT / 'scripts/package/consolidated-rootfs.py')
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)
REG = stat.S_IFREG | 0o755
LINK = stat.S_IFLNK | 0o777


def prepare(tmp_path, monkeypatch, legacy=False):
    files = {name: (REG, b'\x7fELFconsumer') for name in overlay.native_iio.CONSUMERS}
    files.update({
        'usr/lib/libiio.so.1.0.0': (REG, b'\x7fELFlibrary'),
        'usr/lib/libiio.so.1': (LINK, b'libiio.so.1.0.0'),
        'usr/lib/libzstd.so.1.5.7': (REG, b'zstd'),
        'etc/default/iiod': (REG, b'old defaults'),
        'etc/keep': (REG, b'unchanged'),
    })
    if legacy:
        files['usr/lib/libiio.so.0'] = REG, b'legacy'
    data = b''
    for index, (name, (mode, payload)) in enumerate(files.items(), 1):
        fields = [index, mode, 0, 0, 1, 1234, 0, 0, 0, 0, 0, 0, 0]
        data += overlay.member(name, fields, payload)
    data += overlay.member('TRAILER!!!', [0] * 13, b'')
    bash, stage, output = (tmp_path / name for name in ('bash', 'stage', 'output'))
    bash.mkdir()
    compressed = gzip.compress(data, mtime=0)
    (bash / 'rootfs.cpio.gz').write_bytes(compressed)
    fields = [0x27051956, 0, 1234, len(compressed), 0, 0, zlib.crc32(compressed), 5, 2, 3, 1, b'fixture']
    header = struct.pack('>7I4B32s', *fields)
    fields[1] = zlib.crc32(header)
    (bash / 'rootfs.cpio.uboot').write_bytes(struct.pack('>7I4B32s', *fields) + compressed)
    for name, payload in [('usr/sbin/iiod', b'\x7fELFconsumer'),
                          ('usr/lib/libiio.so.1.0.0', b'\x7fELFlibrary'),
                          ('usr/lib/libzstd.so.1.5.7', b'new zstd')]:
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    hashes = {name: hashlib.sha256(((bash if name.startswith('rootfs.') else stage) / name).read_bytes()).hexdigest()
              for name in overlay.INPUT_NAMES}
    manifest = tmp_path / 'inputs.json'
    manifest.write_text(json.dumps(hashes))
    monkeypatch.setattr(sys, 'argv', ['overlay', '--bash-images', str(bash), '--iiod-stage', str(stage),
                                     '--build-inputs', str(manifest), '--output', str(output)])
    monkeypatch.setattr(overlay.native_iio, 'elf_needed', lambda data, tool:
                        {'libiio.so.1'} if data == b'\x7fELFconsumer' else set())
    return data, stage, output


def test_native_overlay_preserves_unrelated_members_and_valid_uimage(tmp_path, monkeypatch):
    original, stage, output = prepare(tmp_path, monkeypatch)
    overlay.main()
    result = overlay.entries((output / 'rootfs.cpio').read_bytes())
    assert result['etc/keep'][3] == overlay.entries(original)['etc/keep'][3]
    assert result['usr/lib/libzstd.so.1.5.7'][2] == b'new zstd'
    assert result['usr/lib/libiio.so.1'][2] == b'libiio.so.1.0.0'
    assert not any('0.26' in name or name.startswith('opt/') for name in result)
    image = (output / 'rootfs.cpio.uboot').read_bytes()
    fields = list(struct.unpack('>7I4B32s', image[:64]))
    crc, fields[1] = fields[1], 0
    assert zlib.crc32(struct.pack('>7I4B32s', *fields)) == crc
    assert fields[3] == len(image[64:])
    assert fields[6] == zlib.crc32(image[64:])
    assert json.loads((output / 'manifest.json').read_text())['native_iio']['libiio_abi'] == 1


def test_legacy_rootfs_is_rejected_before_writing_output(tmp_path, monkeypatch):
    _, _, output = prepare(tmp_path, monkeypatch, legacy=True)
    with pytest.raises(ValueError, match='Legacy libiio artifact'):
        overlay.main()
    assert not output.exists()


def test_changed_candidate_is_rejected_before_writing_output(tmp_path, monkeypatch):
    _, stage, output = prepare(tmp_path, monkeypatch)
    (stage / 'usr/sbin/iiod').write_bytes(b'changed')
    with pytest.raises(ValueError, match='Unqualified input'):
        overlay.main()
    assert not output.exists()
