#!/usr/bin/env python3
"""Collect corresponding software sources and notices; do not authorize binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
ARM_SOURCE = {
    'url': 'https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/srcrel/arm-gnu-toolchain-src-snapshot-14.2.rel1.tar.xz',
    'sha256': 'e6405f20f8a817a50d92dbf7974d0ee77708dfdf9e79900a59c5d343b464ef9c',
    'hash_source': 'https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/srcrel/arm-gnu-toolchain-src-snapshot-14.2.rel1.tar.xz.sha256asc',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('work', type=Path)
    a = p.parse_args()
    work = a.work.resolve()
    output = work / 'package/source-materials'
    if output.exists():
        p.error('Source-materials output already exists; preserve it and use a new build/output')
    legal = work / 'bash/edge-userspace-output/legal-info'
    if not (legal / 'manifest.csv').exists():
        p.error('Complete the userspace all/legal-info stage first')
    # Do not sweep untracked local files, credentials or recordings into a bundle.
    tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).decode().split('\0')
    subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', 'HEAD'], check=True)
    project_commit = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    downloads = work / 'source-downloads'
    downloads.mkdir(exist_ok=True)
    arm = downloads / ARM_SOURCE['url'].rsplit('/', 1)[1]
    if not arm.exists():
        partial = arm.with_suffix('.partial')
        with urllib.request.urlopen(ARM_SOURCE['url'], timeout=120) as response, partial.open('wb') as target:
            while block := response.read(1024 * 1024):
                target.write(block)
        partial.rename(arm)
    if digest(arm) != ARM_SOURCE['sha256']:
        raise ValueError('Arm corresponding-source archive mismatch')
    output.mkdir(parents=True)
    # Materialize any download-cache links so the collection is self-contained.
    shutil.copytree(legal, output / 'buildroot-legal-info', symlinks=False)
    shutil.copy2(arm, output / arm.name)
    toolchain = work / 'baseline/edge-userspace-output/host/opt/ext-toolchain'
    for name in ('license.txt', '14.2.rel1-x86_64-arm-none-linux-gnueabihf-manifest.txt'):
        shutil.copy2(toolchain / name, output / ('arm-' + name))
    sources = {
        'kernel': work / 'next/kernel612/modern-linux',
        'buildroot-2026.08': work / 'bash/modern-buildroot',
        'buildroot-sdk14-recipes': work / 'baseline/modern-buildroot',
        'br2-external': work / 'bash/modern-br2-external',
        'libiio-upstream': work / 'next/libiio-1.0',
    }
    revisions = {}
    for name, source in sources.items():
        revisions[name] = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        with (output / (name + '.tar.gz')).open('wb') as target:
            subprocess.run(['git', '-C', str(source), 'archive', '--format=tar.gz',
                            '--prefix=' + name + '/', 'HEAD'], stdout=target, check=True)
        (output / (name + '.patch')).write_bytes(subprocess.check_output(
            ['git', '-C', str(source), 'diff', '--binary', 'HEAD']))
        added = subprocess.check_output(['git', '-C', str(source), 'ls-files',
                                         '--others', '--exclude-standard', '-z']).decode().split('\0')
        with tarfile.open(output / (name + '-added.tar.gz'), 'w:gz') as tar:
            for entry in sorted(filter(None, added)):
                tar.add(source / entry, arcname=name + '/' + entry, recursive=False)
    with tarfile.open(output / 'libiio-prepared.tar.gz', 'w:gz') as tar:
        tar.add(work / 'perf/libiio1-source', arcname='libiio-prepared')
    shutil.copy2(work / 'next/zstd-1.5.7.tar.gz', output / 'zstd-1.5.7.tar.gz')
    with tarfile.open(output / 'project.tar.gz', 'w:gz') as tar:
        for name in sorted(filter(None, tracked)):
            tar.add(ROOT / name, arcname='project/' + name, recursive=False)
    config = output / 'build-configs'
    config.mkdir()
    for name, path in {
        'kernel.config': work / 'next/kernel612/edge-kernel-output/.config',
        'sdk14.config': work / 'baseline/edge-userspace-output/.config',
        'rootfs.config': work / 'bash/edge-userspace-output/.config',
        'iiod-cmake.txt': work / 'perf/libiio1-build/CMakeCache.txt',
    }.items():
        shutil.copy2(path, config / name)
    report = {'status': 'SOFTWARE SOURCE MATERIALS COLLECTED; NOT BINARY RELEASE CLEARANCE',
              'project_commit': project_commit,
              'source_revisions': revisions, 'arm_sources': ARM_SOURCE,
              'remaining': ['Review the actual target runtime license inventory',
                            'Collect/reconcile vendor BOOT.BIN, FSBL and FPGA corresponding sources/notices',
                            'Qualify the exact SD artifact on hardware'],
              'files': {str(path.relative_to(output)): digest(path)
                        for path in sorted(output.rglob('*')) if path.is_file()}}
    (output / 'inventory.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'files': len(report['files'])}, indent=2))


if __name__ == '__main__':
    main()
