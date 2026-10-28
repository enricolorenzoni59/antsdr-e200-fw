#!/usr/bin/env python3
"""Check a new release identity, or upload verified assets to an unpublished draft."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('assets', ROOT / 'scripts/package/release-assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)
NAMES = {'e200-sd.img.xz', 'e200-sd.img.xz.sha256', 'source-materials.tar.gz',
         'build-manifest.json', 'sd-manifest.json', 'release-manifest.json',
         'QUICKSTART.md', 'RELEASE.md', 'SHA256SUMS'}


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def optional(endpoint):
    result = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
    if result.returncode == 0:
        return json.loads(result.stdout)
    if '(HTTP 404)' in result.stderr:
        return None
    raise RuntimeError('GitHub API check failed: ' + result.stderr.strip())


def release_for_tag(repo, tag):
    # /releases/tags/{tag} omits unpublished drafts without a Git tag.
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/releases?per_page=100'))
    matches = [r for page in pages for r in page if r['tag_name'] == tag]
    if len(matches) > 1:
        raise ValueError('Multiple releases use this tag; inspect them before retrying')
    return matches[0] if matches else None


def check(repo, tag, commit):
    assets.validate_identity(tag, commit)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Expected owner/repository')
    if (optional(f'repos/{repo}/git/ref/tags/{tag}') is not None
            or release_for_tag(repo, tag) is not None):
        raise ValueError('Tag or release already exists; choose a new tag')


def upload(repo, tag, commit, folder):
    check(repo, tag, commit)
    if set(p.name for p in folder.iterdir()) != NAMES:
        raise ValueError('Unexpected or missing release assets')
    if any(p.is_symlink() or not p.is_file() for p in folder.iterdir()):
        raise ValueError('Release assets must be regular files')
    checksums = {}
    for line in (folder / 'SHA256SUMS').read_text().splitlines():
        value, name = line.split('  ', 1)
        if name in checksums or name not in NAMES - {'SHA256SUMS'}:
            raise ValueError('Invalid checksum inventory')
        checksums[name] = value
    if set(checksums) != NAMES - {'SHA256SUMS'}:
        raise ValueError('Incomplete checksum inventory')
    for name in NAMES:
        path = folder / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > assets.MAX_ASSET_BYTES:
            raise ValueError('Invalid release asset: ' + name)
        if name in checksums and assets.digest(path) != checksums[name]:
            raise ValueError('Release checksum mismatch: ' + name)
    manifest = json.loads((folder / 'release-manifest.json').read_text())
    if manifest['source_commit'] != commit or manifest['tag'] != tag:
        raise ValueError('Release assets and requested identity differ')
    gh('release', 'create', tag, '--repo', repo, '--target', commit,
       '--draft', '--prerelease', '--latest=false', '--title', f'E200 {tag} — review required',
       '--notes-file', str(folder / 'RELEASE.md'), *[str(folder / name) for name in sorted(NAMES)])
    release = release_for_tag(repo, tag)
    if not release or not release['draft'] or not release['prerelease'] or release['target_commitish'] != commit:
        raise RuntimeError('Unexpected release state; inspect the release before taking further action')
    remote = {a['name']: a for a in release['assets']}
    if set(remote) != NAMES:
        raise RuntimeError('Draft has missing or unexpected assets')
    for name, item in remote.items():
        path = folder / name
        if item['size'] != path.stat().st_size:
            raise RuntimeError('Uploaded size mismatch: ' + name)
        if item.get('digest') and item['digest'] != 'sha256:' + assets.digest(path):
            raise RuntimeError('Uploaded digest mismatch: ' + name)
    print(release['html_url'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--assets', type=Path, help='Omit for a read-only preflight check')
    args = parser.parse_args()
    branch = os.environ['GITHUB_DEFAULT_BRANCH']
    if os.environ['GITHUB_REF'] != 'refs/heads/' + branch or os.environ['GITHUB_SHA'] != args.commit:
        raise ValueError('Run this workflow from the default branch at its dispatch SHA')
    if subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip() != args.commit:
        raise ValueError('Checkout and dispatch commit differ')
    # GITHUB_TOKEN cannot create a release when its target workflow files differ
    # from the default branch. Recheck after a long build if that branch moved.
    subprocess.run(['git', '-C', str(ROOT), 'fetch', '--no-tags', 'origin',
                    f'+refs/heads/{branch}:refs/remotes/origin/{branch}'], check=True)
    subprocess.run(['git', '-C', str(ROOT), 'diff', '--exit-code', args.commit,
                    'refs/remotes/origin/' + branch, '--', '.github/workflows'], check=True)
    if args.assets:
        upload(args.repo, args.tag, args.commit, args.assets.resolve())
    else:
        check(args.repo, args.tag, args.commit)
