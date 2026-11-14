"""Signal native Heat; token chi trong file root-only, khong argv/log."""
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

from controls import check_rule
from fetch_secrets import endpoint
from readiness import probe
from runtime import (Deadline, Failure, STATE, active_state, atomic_json, boot_id,
                     cli, command, private_dir, read_json)


def signal_endpoint(url):
    endpoint(url)
    parts = urlsplit(url)
    if (not parts.path.startswith('/heat-api/') or '\n' in url or '\r' in url
            or any(c.isspace() for c in url)):
        raise Failure('invalid-signal-endpoint')
    return url


def send_status(config_path=STATE / 'signal.json', state_dir=STATE, status='SUCCESS', *, run=command):
    if status not in ('SUCCESS', 'FAILURE'):
        raise Failure('invalid-signal-status')
    state_dir, config_path = Path(state_dir), Path(config_path)
    private_dir(state_dir)
    # Cung lock cho OnFailure va success, tranh hai terminal signal trai nhau.
    lock_path = state_dir / 'heat-signal.lock'
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        attempt = read_json(state_dir / 'heat-attempt.json')
        if attempt['boot_id'] != boot_id():
            raise Failure('stale-heat-attempt')
        sent_path = state_dir / 'heat-sent.json'
        if sent_path.exists():
            if read_json(sent_path).get('status') != status:
                raise Failure('terminal-signal-conflict')
            return
        deadline = Deadline(attempt['deadline'])
        if status == 'SUCCESS':
            deadline.remaining()
            state = active_state(state_dir)
            if (state['started'] < attempt['started'] or
                    any(read_json(state_dir / (name + '.json')) != state for name in ('guard', 'ready'))):
                raise Failure('stale-or-missing-ready')
            deadline = Deadline(min(attempt['deadline'], state['deadline']))
        else:
            # Bao FAILURE ke ca readiness da het han; khong cho SUCCESS them budget.
            deadline = Deadline(time.monotonic() + 5)
        chosen_path = state_dir / 'heat-chosen.json'
        if chosen_path.exists() and read_json(chosen_path).get('status') != status:
            raise Failure('terminal-signal-conflict')
        config = read_json(config_path)
        url = signal_endpoint(config['endpoint'])
        if not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,8192}', config['token']):
            raise Failure('invalid-signal-token')
        reason = 'ready' if status == 'SUCCESS' else 'bootstrap-failed'
        payload = json.dumps({'status': status, 'reason': reason, 'data': attempt['instance_id']}).encode()
        attempted = False
        try:
            with tempfile.TemporaryDirectory(prefix='heat-http-', dir=state_dir) as temp:
                header = Path(temp) / 'auth'
                header.touch(mode=0o600)
                header.write_text('X-Auth-Token: ' + config['token'] + '\n')
                for i in range(3):
                    if status == 'SUCCESS':
                        # Retry cung la mot SUCCESS moi: khong tin snapshot truoc HTTP503.
                        if active_state(state_dir) != state or any(
                                read_json(state_dir / (name + '.json')) != state for name in ('guard','ready')):
                            raise Failure('stale-ready-on-retry')
                        check_rule(run)
                        if not probe(deadline, run=run):
                            raise Failure('not-ready-at-signal')
                    argv = ['curl', '--disable', '--silent', '--show-error', '--noproxy', '*',
                            '--max-time', str(deadline.remaining()), '--output', '/dev/null',
                            '--write-out', '%{http_code}', '--request', 'POST',
                            '--header', '@' + str(header), '--header', 'Content-Type: application/json',
                            '--data-binary', '@-', url]
                    remaining = deadline.remaining()
                    atomic_json(chosen_path, {'status': status})
                    attempted = True
                    result = run(argv, input=payload, timeout=remaining)
                    if result.returncode == 0 and result.stdout == b'200':
                        deadline.remaining()
                        atomic_json(sent_path, dict(status=status, boot_id=attempt['boot_id'],
                                                    instance_id=attempt['instance_id']))
                        return
                    if result.stdout not in (b'000', b'429', b'500', b'502', b'503', b'504'):
                        break
                    if i < 2:
                        time.sleep(min(0.1, deadline.remaining()))
            raise Failure('signal-not-acknowledged')
        finally:
            # Ca loi transport cung dong kin: Heat timeout, token local khong luu lai.
            # Chua POST (vd live probe loi) thi giu token cho OnFailure bao FAILURE.
            if attempted:
                config_path.unlink(missing_ok=True)


if __name__ == '__main__':
    import sys
    status = 'FAILURE' if sys.argv[1:] == ['--failure'] else 'SUCCESS'
    cli(lambda: send_status(status=status))
