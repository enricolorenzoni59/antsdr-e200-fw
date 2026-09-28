#!/usr/bin/env python3
"""Fetch an immutable experimental ADI component and apply only its local series."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def git(path, *args):
    return subprocess.run(['git', '-C', str(path), *args], check=True,
                          stdout=subprocess.PIPE, text=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=['linux', 'buildroot', 'br2-external'])
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / 'configs/edge.lock.json').read_text())
    entry = lock['components'][args.component]
    dest = args.destination or ROOT / 'work/upstream' / ('modern-' + args.component)
    if not dest.exists():
        dest.mkdir(parents=True)
        git(dest, 'init')
        git(dest, 'remote', 'add', 'origin', entry['repo'])
        git(dest, 'fetch', '--depth', '1', 'origin', entry['commit'])
        git(dest, 'checkout', '--detach', 'FETCH_HEAD')
    actual = git(dest, 'rev-parse', 'HEAD')
    if actual != entry['commit']:
        raise SystemExit(f'Unexpected revision {actual}; no reset performed')
    series = ROOT / 'patches' / args.component / 'series'
    patches = []
    if series.exists():
        for line in series.read_text().splitlines():
            if line.strip() and not line.startswith('#'):
                path = series.parent / line.strip()
                patches.append(path)
        command = ['git', '-C', str(dest), 'apply', '--check', *map(str, patches)]
        forward = subprocess.run(command, capture_output=True)
        if forward.returncode == 0:
            git(dest, 'apply', *map(str, patches))
        else:
            reverse = subprocess.run(command[:4] + ['--reverse'] + command[4:], capture_output=True)
            if reverse.returncode:
                raise SystemExit('Patch state differs from the recorded series; no reset performed:\n' + forward.stderr.decode())
    report = {'component': args.component, **entry, 'patches': {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in patches},
        'status': 'SOURCE PREPARATION ONLY', 'hardware_validated': False}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
