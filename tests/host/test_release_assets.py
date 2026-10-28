"""Exercise byte integrity and the draft-only upload boundary without GitHub writes."""
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path
from types import SimpleNamespace
import tarfile
import os
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts/package' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundle = load('release-assets')
draft = load('release-draft')
COMMIT = '1' * 40
TAG = 'v0.1.0-rc1'


@pytest.fixture
def inputs(tmp_path):
    work = tmp_path / 'work'
    sd = work / 'package/sd'
    sd.mkdir(parents=True)
    image = b'fixture image\0' * 1024
    (sd / 'e200-sd.img').write_bytes(image)
    (sd / 'e200-qspi.itb').write_bytes(b'not a release asset')
    recorded = {'bytes': len(image), 'sha256': hashlib.sha256(image).hexdigest()}
    (sd / 'manifest.json').write_text(json.dumps({'artifacts': {'e200-sd.img': recorded}}))
    files = {name: bundle.digest(ROOT / name) for name in
             ['scripts/package/release-package.py', 'configs/release.lock.json']}
    (work / 'package/build-manifest.json').write_text(json.dumps({'source_files': files}))
    source = work / 'package/source-materials'
    source.mkdir()
    (source / 'project.tar.gz').write_bytes(b'source fixture')
    (source / 'inventory.json').write_text(json.dumps({'project_commit': COMMIT,
        'files': {'project.tar.gz': bundle.digest(source / 'project.tar.gz')}}))
    return work, tmp_path / 'assets', image


def test_complete_bundle_checksums_sources_and_draft_state(inputs):
    work, out, image = inputs
    bundle.prepare(work, out, TAG, COMMIT)
    assert {p.name for p in out.iterdir()} == draft.NAMES
    assert lzma.open(out / 'e200-sd.img.xz').read() == image
    for line in (out / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ')
        assert bundle.digest(out / name) == expected
    with tarfile.open(out / 'source-materials.tar.gz') as archive:
        assert archive.extractfile('source-materials/project.tar.gz').read() == b'source fixture'
    status = json.loads((out / 'release-manifest.json').read_text())
    assert status['source_commit'] == COMMIT
    assert not status['hardware_validated'] and not status['redistribution_review_complete']


@pytest.mark.parametrize('failure', ['image', 'source-commit', 'extra-source', 'source-bytes', 'symlink', 'build-source'])
def test_mixed_or_tampered_inputs_fail_before_output(inputs, failure):
    work, out, _ = inputs
    sources = work / 'package/source-materials'
    if failure == 'image':
        (work / 'package/sd/e200-sd.img').write_bytes(b'changed')
    elif failure == 'source-commit':
        p = sources / 'inventory.json'
        q = json.loads(p.read_text()); q['project_commit'] = '2' * 40; p.write_text(json.dumps(q))
    elif failure == 'extra-source':
        (sources / 'unlisted-private-file').write_text('must not be uploaded')
    elif failure == 'source-bytes':
        (sources / 'project.tar.gz').write_bytes(b'changed')
    elif failure == 'symlink':
        (sources / 'linked').symlink_to(work / 'package/sd/e200-sd.img')
    else:
        p = work / 'package/build-manifest.json'
        q = json.loads(p.read_text()); q['source_files']['configs/release.lock.json'] = '0' * 64
        p.write_text(json.dumps(q))
    with pytest.raises(ValueError):
        bundle.prepare(work, out, TAG, COMMIT)
    assert not out.exists()


@pytest.mark.parametrize('tag', ['--draft=false', '../escape', 'a..b', 'a.lock', 'a.', '$(id)', 'a\nb'])
def test_invalid_release_tags_are_rejected(tag):
    with pytest.raises(ValueError):
        bundle.validate_identity(tag, COMMIT)


@pytest.mark.parametrize('remote_error', [None, 'missing', 'digest', 'published'])
def test_upload_is_always_draft_and_exact_commit(inputs, monkeypatch, remote_error):
    work, out, _ = inputs
    bundle.prepare(work, out, TAG, COMMIT)
    monkeypatch.setattr(draft, 'optional', lambda endpoint: None)
    calls = []
    def gh(*args):
        calls.append(args)
        if args[0] == 'release':
            return 'draft URL'
        if not any(c[:2] == ('release', 'create') for c in calls):
            return '[[]]'
        release = {'tag_name': TAG, 'draft': True, 'prerelease': True, 'target_commitish': COMMIT,
            'html_url': 'draft URL', 'assets': [dict(name=p.name, size=p.stat().st_size,
            digest='sha256:' + bundle.digest(p)) for p in out.iterdir()]}
        if remote_error == 'missing': release['assets'].pop()
        if remote_error == 'digest': release['assets'][0]['digest'] = 'sha256:' + '0' * 64
        if remote_error == 'published': release['draft'] = False
        return json.dumps([[release]])
    monkeypatch.setattr(draft, 'gh', gh)
    if remote_error:
        with pytest.raises(RuntimeError): draft.upload('owner/repo', TAG, COMMIT, out)
    else:
        draft.upload('owner/repo', TAG, COMMIT, out)
    create = next(c for c in calls if c[:2] == ('release', 'create'))
    assert '--draft' in create and '--prerelease' in create and '--latest=false' in create
    assert create[create.index('--target') + 1] == COMMIT


def test_existing_tag_never_creates_a_release(monkeypatch):
    monkeypatch.setattr(draft, 'optional', lambda endpoint: {'ref': 'existing'})
    with pytest.raises(ValueError, match='already exists'):
        draft.check('owner/repo', TAG, COMMIT)


def test_changed_asset_never_reaches_upload(inputs, monkeypatch):
    work, out, _ = inputs
    bundle.prepare(work, out, TAG, COMMIT)
    (out / 'e200-sd.img.xz').write_bytes(b'changed')
    monkeypatch.setattr(draft, 'optional', lambda endpoint: None)
    def gh(*args):
        assert args[0] == 'api', 'Must not upload'
        return '[[]]'
    monkeypatch.setattr(draft, 'gh', gh)
    with pytest.raises(ValueError, match='checksum mismatch'):
        draft.upload('owner/repo', TAG, COMMIT, out)


def test_api_auth_failure_is_not_treated_as_absent_tag(monkeypatch):
    monkeypatch.setattr(draft.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stderr='Forbidden (HTTP 403)'))
    with pytest.raises(RuntimeError, match='API check failed'):
        draft.optional('repos/owner/repo/git/ref/tags/new')


def test_existing_draft_without_git_tag_is_rejected(monkeypatch):
    monkeypatch.setattr(draft, 'optional', lambda endpoint: None)
    monkeypatch.setattr(draft, 'gh', lambda *args: json.dumps([[{'tag_name': TAG, 'draft': True}]]))
    with pytest.raises(ValueError, match='already exists'):
        draft.check('owner/repo', TAG, COMMIT)


def test_wrong_release_commit_never_reaches_upload(inputs, monkeypatch):
    work, out, _ = inputs
    bundle.prepare(work, out, TAG, COMMIT)
    monkeypatch.setattr(draft, 'optional', lambda endpoint: None)
    def gh(*args):
        assert args[0] == 'api', 'Must not upload'
        return '[[]]'
    monkeypatch.setattr(draft, 'gh', gh)
    with pytest.raises(ValueError, match='identity differ'):
        draft.upload('owner/repo', TAG, '2' * 40, out)


def test_workflow_cli_refuses_a_feature_branch_before_network():
    env = dict(os.environ, GITHUB_DEFAULT_BRANCH='main', GITHUB_REF='refs/heads/feature', GITHUB_SHA=COMMIT)
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/package/release-draft.py'),
                            '--repo', 'owner/repo', '--tag', TAG, '--commit', COMMIT],
                            env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Run this workflow from the default branch' in result.stderr
