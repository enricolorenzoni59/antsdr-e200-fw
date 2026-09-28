#!/usr/bin/env python3
"""Package a fresh public-source build and record its exact input identities."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    work = Path(sys.argv[1])
    output = work / 'package'
    bash = work / 'bash/edge-userspace-output/images'
    stage = work / 'perf/libiio1-stage'
    spec = importlib.util.spec_from_file_location('overlay', ROOT / 'scripts/package/consolidated-rootfs.py')
    overlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlay)
    pins = {name: hashlib.sha256(((bash if name.startswith('rootfs.') else stage) / name).read_bytes()).hexdigest()
            for name in overlay.PINS}
    output.mkdir(exist_ok=True)
    pinfile = output / 'new-build-inputs.json'
    pinfile.write_text(json.dumps(pins, indent=2) + '\n')
    def run(script, *args):
        subprocess.run(['python3', str(ROOT / 'scripts/package' / script), *map(str, args)], check=True)
    run('consolidated-rootfs.py', '--bash-images', bash, '--iiod-stage', stage,
        '--build-inputs', pinfile, '--output', output / 'rootfs')
    run('release-ram.py', '--kernel', work / 'next/kernel612/edge-kernel-output',
        '--rootfs', output / 'rootfs', '--fpga', work / 'vendor/system_top.bit', '--output', output / 'ram')
    run('storage-images.py', '--ram-package', output / 'ram', '--input-manifest', output / 'ram/manifest.json',
        '--boot-bin', work / 'vendor/BOOT.BIN', '--tools', '/usr/bin', '--dtc', '/usr/bin/dtc',
        '--profile', 'iq24', '--output', output / 'sd')
    manifest = {'status': 'BUILT; HARDWARE UNTESTED; REDISTRIBUTION REVIEW PENDING',
                'historical_rootfs_inputs_match': pins == overlay.PINS,
                'vendor_boot': 'official v0.39; differs from historical lab-built BOOT.BIN',
                'locks': {}, 'source_files': {}}
    for folder in ('configs', 'patches', 'profiles', 'board', 'scripts', 'containers', 'tests'):
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                manifest['source_files'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted((ROOT / 'configs').glob('*.json')):
        manifest['locks'][path.name] = json.loads(path.read_text())
    (output / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
