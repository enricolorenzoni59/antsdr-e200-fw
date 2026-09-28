"""Reject corrupt or ambiguous vendor inputs before writing boot files."""
import hashlib
import importlib.util
from pathlib import Path
import zipfile
import pytest

spec = importlib.util.spec_from_file_location('release_fetch', Path(__file__).resolve().parents[2] / 'scripts/build/fetch-release.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(tmp_path, duplicate=False):
    payloads = {'build_sdimg/BOOT.bin': b'boot', 'build/system_top.bit': b'fpga'}
    archive = tmp_path / 'vendor.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name, data in payloads.items():
            z.writestr('e200/' + name, data)
        if duplicate:
            z.writestr('other/build_sdimg/BOOT.bin', b'boot')
    lock = {'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'files': [{'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                      for name, data in payloads.items()]}
    out = tmp_path / 'out'
    out.mkdir()
    return archive, out, lock


def test_verified_prefixed_archive(tmp_path):
    archive, out, lock = fixture(tmp_path)
    module.vendor_files(archive, out, lock)
    assert (out / 'BOOT.BIN').read_bytes() == b'boot'
    assert (out / 'system_top.bit').read_bytes() == b'fpga'


def test_corrupt_archive_rejected_without_output(tmp_path):
    archive, out, lock = fixture(tmp_path)
    archive.write_bytes(archive.read_bytes() + b'corruption')
    with pytest.raises(ValueError, match='SHA256'):
        module.vendor_files(archive, out, lock)
    assert not list(out.iterdir())


def test_ambiguous_boot_member_rejected(tmp_path):
    archive, out, lock = fixture(tmp_path, duplicate=True)
    with pytest.raises(ValueError, match='Expected one'):
        module.vendor_files(archive, out, lock)
    assert not list(out.iterdir())


def test_wrong_member_hash_rejected(tmp_path):
    archive, out, lock = fixture(tmp_path)
    lock['files'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='member mismatch'):
        module.vendor_files(archive, out, lock)
    assert not list(out.iterdir())
