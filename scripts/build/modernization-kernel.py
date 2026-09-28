#!/usr/bin/env python3
"""Prepare an isolated ADI+stable IQ24 kernel inside the kernel Docker builder."""
import concurrent.futures
import hashlib
import json
import lzma
from pathlib import Path
import re
import subprocess
import urllib.request

root = Path('/next/kernel612')
project = Path('/project')
lock = json.loads((project / 'configs/modernization.lock.json').read_text())
expected_downloads = {p['url']: p['sha256'] for p in lock['kernel']['stable_patches']}
root.mkdir(parents=True, exist_ok=True)
downloads = root / 'downloads'
downloads.mkdir(exist_ok=True)


def fetch(n):
    name = f'patch-6.12.{n}-{n+1}.xz'
    url = 'https://cdn.kernel.org/pub/linux/kernel/v6.x/incr/' + name
    archive = downloads / name
    if not archive.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read()
        lzma.decompress(data)  # Reject incomplete/error downloads before saving.
        archive.write_bytes(data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != expected_downloads[url]:
        raise SystemExit(f'Unexpected stable patch hash: {url}')
    patch = archive.with_suffix('')
    patch.write_bytes(lzma.decompress(archive.read_bytes()))
    return {'url': url, 'sha256': digest,
            'patch': str(patch)}


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    patches = list(pool.map(fetch, range(77, 111)))
(root / 'downloads.json').write_text(json.dumps(patches, indent=2) + '\n')
source = root / 'modern-linux'
if not source.exists():
    subprocess.run(['git', 'clone', '--no-hardlinks', '/baseline/modern-linux', str(source)], check=True)
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == 'bf1d49f17fa9e15bc40be2615ef67cdf023f660a'
progress = root / 'stable-progress.json'
done = json.loads(progress.read_text()) if progress.exists() else []
for n, entry in enumerate(patches, 77):
    if n in done:
        continue
    print('APPLY', entry['url'], flush=True)
    check = subprocess.run(['git', '-C', str(source), 'apply', '--check', entry['patch']], capture_output=True, text=True)
    excludes = []
    merged = {}
    if check.returncode:
        paths = sorted(set(re.findall(r'error: patch failed: (.*):\d+', check.stderr) +
                           re.findall(r'error: (.*): No such file or directory', check.stderr)))
        if not paths:
            raise SystemExit(check.stderr)
        for path in paths:
            resolution = project / 'patches/modernization' / f'6.12.{n}-{n+1}' / (path.replace('/', '__') + '.patch')
            not_applicable = resolution.with_suffix('.skip')
            if not_applicable.exists():
                expected = not_applicable.read_text().splitlines()[0]
                actual = hashlib.sha256((source / path).read_bytes()).hexdigest()
                if actual != expected:
                    raise SystemExit(f'Unexpected source for documented non-applicable change: {path}')
                print('NOT APPLICABLE:', path, not_applicable.read_text(), flush=True)
                excludes.append('--exclude=' + path)
                continue
            if resolution.exists():
                subprocess.run(['git', '-C', str(source), 'apply', '--check', str(resolution)], check=True)
                excludes.append('--exclude=' + path)
                merged[path] = resolution
                continue
            scratch = root / 'merges' / str(n) / path
            scratch.parent.mkdir(parents=True, exist_ok=True)
            ours = scratch.with_name(scratch.name + '.ours')
            ours.write_bytes((source / path).read_bytes())
            versions = []
            for version, suffix in ((n, '.base'), (n+1, '.theirs')):
                dest = scratch.with_name(scratch.name + suffix)
                url = f'https://raw.githubusercontent.com/gregkh/linux/v6.12.{version}/{path}'
                with urllib.request.urlopen(url, timeout=60) as response:
                    dest.write_bytes(response.read())
                versions.append(dest)
            result = subprocess.run(['git', 'merge-file', '-p', str(ours), *map(str, versions)], capture_output=True)
            scratch.write_bytes(result.stdout)
            if result.returncode:
                raise SystemExit(f'Conflict requires review: {scratch}')
            merged[path] = result.stdout
            excludes.append('--exclude=' + path)
        subprocess.run(['git', '-C', str(source), 'apply', '--check', *excludes, entry['patch']], check=True)
    subprocess.run(['git', '-C', str(source), 'apply', *excludes, entry['patch']], check=True)
    for path, data in merged.items():
        if isinstance(data, Path):
            subprocess.run(['git', '-C', str(source), 'apply', str(data)], check=True)
        else:
            (source / path).write_bytes(data)
    done.append(n)
    progress.write_text(json.dumps(done) + '\n')
for patch in sorted((project / 'patches/modernization/post-stable').glob('*.patch')):
    applied = subprocess.run(['git', '-C', str(source), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
    if applied.returncode:
        subprocess.run(['git', '-C', str(source), 'apply', str(patch)], check=True)
for name in (project / 'patches/linux/series').read_text().splitlines():
    if name.strip() and not name.startswith('#'):
        patch = project / 'patches/linux' / name.strip()
        applied = subprocess.run(['git', '-C', str(source), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
        if applied.returncode:
            subprocess.run(['git', '-C', str(source), 'apply', str(patch)], check=True)
patch = project / 'patches/experimental/0001-iio-page-backed-rx.patch'
applied = subprocess.run(['git', '-C', str(source), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
if applied.returncode:
    subprocess.run(['git', '-C', str(source), 'apply', str(patch)], check=True)
with (root / 'prepared.diff').open('w') as output:
    subprocess.run(['git', '-C', str(source), 'diff'], check=True, stdout=output)
changed = subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only'], text=True).splitlines()
added = subprocess.check_output(['git', '-C', str(source), 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
manifest = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
            if (source / name).is_file() else None for name in sorted(set(changed + added))}
(root / 'prepared-files.json').write_text(json.dumps(manifest, indent=2) + '\n')
for filename, key in (('prepared.diff', 'prepared_diff_sha256'),
                      ('prepared-files.json', 'prepared_files_sha256')):
    if hashlib.sha256((root / filename).read_bytes()).hexdigest() != lock['kernel'][key]:
        raise SystemExit(f'Prepared source differs from the reviewed candidate: {filename}')
print('KERNEL SOURCE PREPARED; no build or hardware claim', flush=True)
