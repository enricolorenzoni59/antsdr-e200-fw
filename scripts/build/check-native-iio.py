#!/usr/bin/env python3
"""Compile the selected IIO stack on Linux and validate its installed ELF ABI.

This checks the actual E200 recipe options with native Linux tools; it does
not replace an ARM Buildroot build or board qualification.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def run(*args):
    subprocess.run(list(map(str, args)), check=True)


def recipe(package, prefix):
    path = str(ROOT / 'profiles/native-iio/recipes' / (package + '.mk')).replace(' ', '\\ ')
    with tempfile.NamedTemporaryFile(mode='w', suffix='.mk') as makefile:
        makefile.write(f'include {path}\n.PHONY: print\nprint:\n'
                       f'\t@printf "%s\\n" $({prefix}_VERSION) $({prefix}_CONF_OPTS)\n')
        makefile.flush()
        result = subprocess.check_output(['make', '--no-print-directory', '-s', '-f', makefile.name, 'print'], text=True)
    version, *options = result.splitlines()
    return version, options


def main():
    if sys.platform != 'linux':
        raise SystemExit('Native ELF validation requires Linux')
    spec = importlib.util.spec_from_file_location('fetch', ROOT / 'scripts/build/fetch-release.py')
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)
    lock = json.loads((ROOT / 'configs/modernization.lock.json').read_text())
    work = ROOT / 'work/native-iio'
    stage = work / 'stage'
    if stage.exists():
        raise SystemExit('Use a fresh work/native-iio directory for this check')
    source = ROOT / 'work/transport/libiio1-source'
    if not (source / '.e200-test-ready').is_file():
        raise SystemExit('Run prepare-transport-tests.py first')
    version, options = recipe('libiio', 'LIBIIO')
    if version != lock['libiio']['tag'].removeprefix('v'):
        raise ValueError('libiio recipe and source lock disagree')
    prefix = stage / 'usr'
    common = [f'-DCMAKE_INSTALL_PREFIX={prefix}', '-DCMAKE_INSTALL_LIBDIR=lib',
              f'-DCMAKE_INSTALL_RPATH={prefix}/lib', '-DCMAKE_BUILD_TYPE=Release']
    build = work / 'libiio-build'
    run('cmake', '-S', source, '-B', build, *common, *options)
    run('cmake', '--build', build, '--parallel', '2')
    run('cmake', '--install', build)
    ad = work / 'libad9361-source'
    version, options = recipe('libad9361-iio', 'LIBAD9361_IIO')
    if version != lock['libad9361']['commit']:
        raise ValueError('libad9361 recipe and source lock disagree')
    fetch.checkout(ad, lock['libad9361']['repo'], version)
    build = work / 'libad9361-build'
    run('cmake', '-S', ad, '-B', build, *common, *options, f'-DCMAKE_PREFIX_PATH={prefix}')
    run('cmake', '--build', build, '--parallel', '2')
    run('cmake', '--install', build)
    run(prefix / 'bin/iio_rwdev', '--version')
    run(sys.executable, ROOT / 'scripts/build/verify-native-iio.py', stage)


if __name__ == '__main__':
    main()
