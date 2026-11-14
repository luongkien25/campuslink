"""Kich hoat CREATE mot lan; config/attempt phai san sang truoc Docker Wants."""
import os
from pathlib import Path
import time
import uuid

from runtime import Failure, STATE, atomic_json, boot_id, cli, command, private_dir, read_json


def activate(config_dir=Path('/etc/campuslink'), state_dir=STATE, *, instance_id=None, run=command):
    config_dir, state_dir = Path(config_dir), Path(state_dir)
    private_dir(config_dir)
    private_dir(state_dir)
    if (config_dir / 'bootstrap.json').exists() or (state_dir / 'heat-attempt.json').exists():
        raise Failure('already-activated')
    if instance_id is None:
        instance_id = Path('/var/lib/cloud/data/instance-id').read_text().strip()
    uuid.UUID(instance_id)
    bootstrap = read_json(config_dir / 'bootstrap.pending.json')
    signal = read_json(config_dir / 'heat.pending.json')
    if signal.pop('readiness_timeout', 180) != 180:
        raise Failure('invalid-readiness-budget')
    # Docker trong image co Wants ready nhung chua co bootstrap.json.
    for argv in (['systemctl', 'stop', 'docker.socket', 'docker.service'],
                 ['systemctl', 'daemon-reload']):
        if run(argv, timeout=45).returncode:
            raise Failure('activation-precondition-failed')
    started = time.monotonic()
    atomic_json(state_dir / 'heat-attempt.json', dict(instance_id=instance_id,
                boot_id=boot_id(), started=started, deadline=started + 180))
    atomic_json(state_dir / 'signal.json', signal)
    (config_dir / 'heat.pending.json').unlink()
    atomic_json(config_dir / 'bootstrap.json', bootstrap)
    (config_dir / 'bootstrap.pending.json').unlink()
    try:
        result = run(['systemctl', 'start', 'campuslink-heat-signal.service'], timeout=185)
        if result.returncode:
            raise Failure('bootstrap-or-signal-failed')
    except Failure:
        run(['systemctl', 'start', 'campuslink-heat-failure.service'], timeout=10)
        raise


if __name__ == '__main__':
    cli(activate)
