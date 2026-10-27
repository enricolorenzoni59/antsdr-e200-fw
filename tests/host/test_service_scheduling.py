import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'service_scheduling', ROOT / 'scripts/build/configure-service-scheduling.py')
scheduling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduling)


def init_scripts(tmp_path):
    directory = tmp_path / 'etc/init.d'
    directory.mkdir(parents=True)
    for name, (_, launch) in scheduling.LAUNCHES.items():
        script = directory / name
        script.write_text('#!/bin/sh\nstart() {\n' + launch +
                          '\t\t--exec /usr/sbin/service -- "$ARGS"\n}\n' +
                          'stop() { start-stop-daemon -K -p /run/service.pid; }\n')
        script.chmod(0o755)
    return directory


def test_install_preserves_lifecycle_permissions_and_is_idempotent(tmp_path):
    directory = init_scripts(tmp_path)
    originals = {p.name: p.read_text() for p in directory.iterdir()}
    scheduling.install(tmp_path)
    first = {p.name: p.read_text() for p in directory.iterdir()}
    for name, (policy, launch) in scheduling.LAUNCHES.items():
        expected = originals[name].replace(
            launch, launch.replace('start-stop-daemon',
                                   f'/usr/sbin/e200-service-start {policy} start-stop-daemon', 1), 1)
        assert first[name] == expected
        assert (directory / name).stat().st_mode & 0o777 == 0o755
    scheduling.install(tmp_path)
    assert {p.name: p.read_text() for p in directory.iterdir()} == first


def test_unknown_init_is_rejected_before_either_script_changes(tmp_path):
    directory = init_scripts(tmp_path)
    script = directory / 'S60iiod'
    script.write_text(script.read_text().replace('--make-pidfile', '--changed-launch'))
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    with pytest.raises(ValueError, match='Unexpected service launch'):
        scheduling.install(tmp_path)
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux scheduling APIs')
def test_ssh_child_inherits_policy_through_exec_without_changing_parent():
    if 0 not in os.sched_getaffinity(0):
        pytest.skip('CPU 0 is outside this test process cpuset')
    before = (os.sched_getscheduler(0), os.getpriority(os.PRIO_PROCESS, 0),
              os.sched_getaffinity(0))
    child = subprocess.run(
        [sys.executable, str(ROOT / 'profiles/iq24/rootfs-overlay/usr/sbin/e200-service-start'),
         'ssh', sys.executable, '-c',
         'import json,os; print(json.dumps([os.sched_getscheduler(0), '
         'os.getpriority(os.PRIO_PROCESS,0), sorted(os.sched_getaffinity(0))]))'],
        check=True, capture_output=True, text=True, timeout=10)
    assert json.loads(child.stdout) == [os.SCHED_IDLE, 19, [0]]
    assert (os.sched_getscheduler(0), os.getpriority(os.PRIO_PROCESS, 0),
            os.sched_getaffinity(0)) == before
