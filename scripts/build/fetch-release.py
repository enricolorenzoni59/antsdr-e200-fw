#!/usr/bin/env python3
"""Fetch the public, immutable inputs for a fresh release build."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def checkout(path, repo, commit):
    path.mkdir(parents=True, exist_ok=True)
    if not (path / '.git').exists():
        subprocess.run(['git', 'init', str(path)], check=True)
        subprocess.run(['git', '-C', str(path), 'fetch', '--depth=1', repo, commit], check=True)
        subprocess.run(['git', '-C', str(path), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
    actual = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != commit:
        raise ValueError(f'Unexpected source revision in {path}; refusing reset')


def vendor_files(archive, output, lock):
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != lock['archive_sha256']:
        raise ValueError('Vendor archive SHA256 mismatch')
    wanted = {'build_sdimg/BOOT.bin': 'BOOT.BIN', 'build/system_top.bit': 'system_top.bit'}
    records = {entry['path']: entry for entry in lock['files']}
    with zipfile.ZipFile(archive) as z:
        for name, target in wanted.items():
            matches = [entry for entry in z.namelist() if entry == name or entry.endswith('/' + name)]
            if len(matches) != 1:
                raise ValueError(f'Expected one vendor member: {name}; found {len(matches)}')
            data = z.read(matches[0])
            if len(data) != records[name]['size'] or hashlib.sha256(data).hexdigest() != records[name]['sha256']:
                raise ValueError(f'Vendor member mismatch: {name}')
            (output / target).write_bytes(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('work', type=Path)
    a = p.parse_args()
    edge = json.loads((ROOT / 'configs/edge.lock.json').read_text())
    modern = json.loads((ROOT / 'configs/modernization.lock.json').read_text())
    for component in ('buildroot', 'br2-external', 'linux'):
        subprocess.run(['python3', str(ROOT / 'scripts/build/fetch-edge.py'), component,
                        '--destination', str(a.work / 'baseline' / ('modern-' + component))], check=True)
    checkout(a.work / 'bash/modern-buildroot', modern['buildroot']['repo'], modern['buildroot']['commit'])
    checkout(a.work / 'next/libiio-1.0', modern['libiio']['repo'], modern['libiio']['commit'])
    output = a.work / 'vendor'
    output.mkdir(exist_ok=True)
    lock = json.loads((ROOT / 'configs/vendor-v039-artifacts.json').read_text())
    archive = output / 'e200.zip'
    if not archive.exists():
        partial = archive.with_suffix('.partial')
        with urllib.request.urlopen(lock['source_url'], timeout=120) as response, partial.open('wb') as out:
            while block := response.read(1024 * 1024):
                out.write(block)
        partial.rename(archive)
    vendor_files(archive, output, lock)
    (output / 'provenance.json').write_text(json.dumps(lock, indent=2) + '\n')


if __name__ == '__main__':
    main()
