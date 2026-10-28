"""Guard the v1-only rootfs, including unexpected third-party ELF consumers."""
import importlib.util
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native', ROOT / 'scripts/build/verify-native-iio.py')
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)
REG = stat.S_IFREG | 0o755
LINK = stat.S_IFLNK | 0o777


def members():
    result = {name: (REG, b'\x7fELFconsumer') for name in native.CONSUMERS}
    result['usr/lib/libiio.so.1.0.0'] = REG, b'\x7fELFlibrary'
    result['usr/lib/libiio.so.1'] = LINK, b'libiio.so.1.0.0'
    return result


@pytest.fixture
def fake_elf(monkeypatch):
    monkeypatch.setattr(native, 'elf_needed', lambda data, tool:
                        {'libiio.so.1'} if data == b'\x7fELFconsumer' else set())


def test_native_consumers_and_relative_library_link(fake_elf):
    assert native.verify(members())['libiio_abi'] == 1


@pytest.mark.parametrize('name', ['usr/lib/libiio.so.0', 'usr/lib/libiio.so.0.26',
                                 'usr/sbin/iiod-0.26', 'usr/bin/iio_readdev',
                                 'usr/bin/iio_writedev', 'opt/e200/libiio1/lib/libiio.so.1'])
def test_legacy_artifacts_are_rejected(fake_elf, name):
    files = members()
    files[name] = REG, b'leftover'
    with pytest.raises(ValueError, match='Legacy libiio artifact'):
        native.verify(files)


def test_missing_native_library_is_rejected(fake_elf):
    files = members()
    del files['usr/lib/libiio.so.1.0.0']
    with pytest.raises(ValueError, match='Missing file'):
        native.verify(files)


def test_non_native_consumer_is_rejected(fake_elf):
    files = members()
    files['usr/bin/iio_rwdev'] = REG, b'wrong executable'
    with pytest.raises(ValueError, match='Expected native'):
        native.verify(files)


def test_hidden_legacy_dependency_is_rejected(monkeypatch):
    files = members()
    files['usr/bin/third-party-app'] = REG, b'\x7fELFlegacy'
    monkeypatch.setattr(native, 'elf_needed', lambda data, tool:
                        {'libiio.so.0'} if data.endswith(b'legacy') else {'libiio.so.1'})
    with pytest.raises(ValueError, match='ELF still needs libiio v0'):
        native.verify(files)


@pytest.mark.parametrize('target', [b'libiio.so.1', b'../../../../outside'])
def test_library_link_cycles_and_escapes_are_rejected(fake_elf, target):
    files = members()
    files['usr/lib/libiio.so.1'] = LINK, target
    with pytest.raises(ValueError):
        native.verify(files)


@pytest.mark.skipif(sys.platform != 'linux' or not shutil.which('cc') or not shutil.which('readelf'),
                    reason='real ELF integration requires Linux cc and readelf')
def test_real_elf_native_and_hidden_legacy_dependency(tmp_path):
    (tmp_path / 'library.c').write_text('int iio_test(void) { return 1; }\n')
    (tmp_path / 'consumer.c').write_text('extern int iio_test(void); int use_iio(void) { return iio_test(); }\n')
    def library(abi):
        path = tmp_path / f'libiio.so.{abi}'
        subprocess.run(['cc', '-shared', '-fPIC', str(tmp_path / 'library.c'),
                        '-Wl,-soname,' + path.name, '-o', str(path)], check=True)
        return path
    def consumer(abi):
        path = tmp_path / f'consumer-{abi}.so'
        subprocess.run(['cc', '-shared', '-fPIC', str(tmp_path / 'consumer.c'),
                        str(library(abi)), '-o', str(path)], check=True)
        return path.read_bytes()
    files = members()
    payload = consumer(1)
    for name in native.CONSUMERS:
        files[name] = REG, payload
    files['usr/lib/libiio.so.1.0.0'] = REG, (tmp_path / 'libiio.so.1').read_bytes()
    assert native.verify(files)['libiio_abi'] == 1
    files['usr/bin/unexpected-consumer'] = REG, consumer(0)
    with pytest.raises(ValueError, match='ELF still needs libiio v0'):
        native.verify(files)
