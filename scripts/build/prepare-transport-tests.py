#!/usr/bin/env python3
"""Prepare the selected libiio patch stack for native sanitizer tests."""
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fetch', Path(__file__).with_name('fetch-release.py'))
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)
lock = json.loads((ROOT / 'configs/modernization.lock.json').read_text())['libiio']
source = ROOT / 'work/transport/libiio1-source'
fetch.checkout(source, lock['repo'], lock['commit'])
profile = ROOT / 'profiles/iq24-v1'
# Match the production recipe: copy helper sources before the patches that edit them.
# A failed preparation is left intact for inspection; use a fresh work/transport.
ready = source / '.e200-test-ready'
inputs = sorted((profile / 'patches').glob('*.patch')) + sorted((profile / 'src').glob('*'))
inputs += [ROOT / 'tests/rf/tcp-transport.c', ROOT / 'tests/rf/tcp-transport.h', Path(__file__)]
fingerprint = hashlib.sha256((lock['commit'] + ''.join(
    str(path.relative_to(ROOT)) + hashlib.sha256(path.read_bytes()).hexdigest()
    for path in inputs)).encode()).hexdigest()
if ready.exists() and ready.read_text().strip() != fingerprint:
    raise SystemExit('Transport fixture inputs changed; use a fresh work/transport directory')
if not ready.exists():
    subprocess.run(['git', '-C', str(source), 'diff', '--exit-code'], check=True)
    for patch in sorted((profile / 'patches').glob('*.patch')):
        number = int(patch.name.split('-')[0])
        files = {}
        if number == 1:
            files['e200-affinity.h'] = profile / 'src/e200-affinity.h'
        if number == 2:
            for name in ('tcp-transport.c', 'tcp-transport.h'):
                files[name] = ROOT / 'tests/rf' / name
            for suffix in ('.c', '.h'):
                files['e200-zerocopy' + suffix] = profile / 'src' / ('e200-zerocopy' + suffix)
        if number == 3:
            for suffix in ('.c', '.h'):
                files['e200-zerocopy' + suffix] = profile / 'src' / ('e200-zerocopy-async' + suffix)
        if number in (7, 8):
            stem = 'e200-legacy-prefetch' if number == 7 else 'e200-legacy-async'
            for suffix in ('.c', '.h'):
                files['e200-legacy-prefetch' + suffix] = profile / 'src' / (stem + suffix)
        if number == 10:
            files['e200-rx-layout.h'] = profile / 'src/e200-rx-layout.h'
        for name, original in files.items():
            shutil.copy2(original, source / 'iiod' / name)
        subprocess.run(['git', '-C', str(source), 'apply', str(patch)], check=True)
    ready.write_text(fingerprint + '\n')
subprocess.run(['cmake', '-S', str(source), '-B', str(source.parent / 'libiio1-build'),
                '-DWITH_USB_BACKEND=OFF', '-DWITH_SERIAL_BACKEND=OFF', '-DWITH_IIOD_USBD=OFF',
                '-DWITH_IIOD_SERIAL=OFF', '-DWITH_AIO=OFF', '-DWITH_DOC=OFF',
                '-DPYTHON_BINDINGS=OFF', '-DCSHARP_BINDINGS=OFF', '-DHAVE_DNS_SD=OFF'], check=True)
