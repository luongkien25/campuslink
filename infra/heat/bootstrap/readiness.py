"""Readiness cuc bo: HTTP 200/pass VA authenticated Redis PONG trong budget chung."""
import json
from pathlib import Path
import time

from controls import check_rule
from runtime import (Deadline, Failure, STATE, active_state, atomic_json, cli,
                     command, read_json)


def probe(deadline, *, run=command):
    result = run(['docker', 'inspect', 'shlink', '--format',
        '{"Status":{{json .State.Status}},"RestartCount":{{.RestartCount}},"NetworkMode":{{json .HostConfig.NetworkMode}}}'],
        timeout=deadline.remaining())
    if result.returncode:
        # Type=exec chi bao wrapper da exec; docker run co the chua tao container.
        # BindsTo dung ready neu app unit fail; deadline chan missing vo han.
        return False
    try:
        info = json.loads(result.stdout)
        if info['RestartCount'] != 0 or info['NetworkMode'] != 'bridge':
            raise Failure('container-exit-restart-or-network')
        if info['Status'] == 'created':
            return False
        if info['Status'] != 'running':
            raise Failure('container-exit-restart-or-network')
    except (ValueError, KeyError, TypeError):
        raise Failure('invalid-container-state') from None
    health = run(['curl', '--disable', '--silent', '--show-error', '--noproxy', '*',
        '--max-time', str(deadline.remaining()), '--max-filesize', '65536',
        '--write-out', '\n%{http_code}', 'http://127.0.0.1:8080/rest/health'], timeout=deadline.remaining())
    try:
        body, status = health.stdout.rsplit(b'\n', 1)
        if health.returncode or status != b'200' or json.loads(body).get('status') != 'pass':
            return False
    except (ValueError, AttributeError):
        return False
    redis = run(['/bin/sh', '/opt/campuslink/redis-probe.sh', '/run/secrets/redis_servers'], timeout=deadline.remaining())
    deadline.remaining()
    return redis.returncode == 0 and redis.stdout.strip() == b'PONG'


def wait_ready(state_dir=STATE, *, run=command):
    state_dir = Path(state_dir)
    (state_dir / 'ready.json').unlink(missing_ok=True)
    state = active_state(state_dir)
    if read_json(state_dir / 'guard.json') != state:
        raise Failure('stale-guard')
    deadline = Deadline(state['deadline'])
    while True:
        check_rule(run)
        if probe(deadline, run=run):
            atomic_json(state_dir / 'ready.json', state)
            return
        time.sleep(min(1, deadline.remaining()))


if __name__ == '__main__':
    cli(wait_ready)
