"""ADR-10: token POST + hai object GET; khong discovery/list/redirect."""
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from urllib.parse import urlsplit

from runtime import (Deadline, Failure, SECRETS, STATE, atomic_json, boot_id,
                     cli, command, private_dir, read_json)

NAMES = ('db_password', 'redis_servers')


def endpoint(url):
    parts = urlsplit(url)
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        raise Failure('numeric-endpoint-required') from None
    if (parts.scheme not in ('http', 'https') or parts.username or parts.password
            or parts.query or parts.fragment or not (address.is_private or address.is_loopback)):
        raise Failure('unsafe-endpoint')
    return url.rstrip('/')


def request(method, url, deadline, *, scratch_dir, payload=None, token=None, limit=65536):
    for attempt in range(3):
        with tempfile.TemporaryDirectory(prefix='campus-http-', dir=scratch_dir) as temp:
            temp = Path(temp)
            for name in ('headers', 'body', 'auth'):
                (temp / name).touch(mode=0o600)
            argv = ['curl', '--disable', '--silent', '--show-error', '--noproxy', '*',
                    '--max-time', str(deadline.remaining()), '--max-filesize', str(limit),
                    '--dump-header', str(temp / 'headers'), '--output', str(temp / 'body'),
                    '--write-out', '%{http_code}', '--request', method]
            if token:
                (temp / 'auth').write_text('X-Auth-Token: ' + token + '\n')
                argv += ['--header', '@' + str(temp / 'auth')]
            if payload is not None:
                argv += ['--header', 'Content-Type: application/json', '--data-binary', '@-']
            result = command(argv + [url], input=payload, timeout=deadline.remaining())
            try:
                code = int(result.stdout)
            except ValueError:
                code = 0
            # stdout chi HTTP status; khong trich stderr/body vao exception.
            if result.returncode == 0 and code in (200, 201):
                body = (temp / 'body').read_bytes()
                if len(body) > limit:
                    raise Failure('oversize-response')
                return body, (temp / 'headers').read_text(errors='replace')
            if code not in (0, 429, 500, 502, 503, 504) or attempt == 2:
                raise Failure('http-request-failed')
        time.sleep(min(0.1 * (attempt + 1), deadline.remaining()))
    raise Failure('http-request-failed')


def clear_managed(directory):
    directory = Path(directory)
    if directory.is_symlink():
        raise Failure('unsafe-secrets-directory')
    if not directory.exists():
        return
    private_dir(directory)
    entries = list(directory.iterdir())
    for entry in entries:
        info = entry.lstat()
        if entry.name not in NAMES or not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise Failure('unexpected-secrets-file')
    for entry in entries:
        entry.unlink()
    directory.rmdir()


def validate(name, data):
    try:
        text = data.decode('ascii').rstrip('\n')
    except UnicodeError:
        raise Failure('invalid-secret-format') from None
    pattern = r'[0-9a-fA-F]{32,256}' if name == 'db_password' else r'tcp://default:[0-9a-fA-F]{32,256}@10\.20\.0\.10:6379'
    if not re.fullmatch(pattern, text) or data.count(b'\n') > 1:
        raise Failure('invalid-secret-format')
    return data


def fetch(config, secret_dir=SECRETS, state_dir=STATE, *, budget=180):
    secret_dir, state_dir = Path(secret_dir), Path(state_dir)
    private_dir(state_dir)
    with (state_dir / 'fetch.lock').open('a') as lock:
        os.chmod(state_dir / 'fetch.lock', 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ('secrets.json', 'guard.json', 'ready.json'):
            (state_dir / name).unlink(missing_ok=True)
        clear_managed(secret_dir)
        started = time.monotonic()
        deadline = Deadline(started + min(budget, 180))
        deadline.remaining()
        auth_url = endpoint(config['keystone_url'])
        swift_url = endpoint(config['swift_account_url'])
        if not urlsplit(auth_url).path.endswith('/v3/auth/tokens') or not re.fullmatch(r'/v1/AUTH_[a-zA-Z0-9]+', urlsplit(swift_url).path):
            raise Failure('invalid-endpoint-path')
        payload = json.dumps({'auth': {'identity': {'methods': ['application_credential'],
            'application_credential': {'id': config['credential_id'], 'secret': config['credential_secret']}}}}).encode()
        body, headers = request('POST', auth_url, deadline, scratch_dir=state_dir, payload=payload)
        try:
            if not isinstance(json.loads(body)['token'], dict):
                raise Failure('invalid-token-response')
        except (ValueError, KeyError, TypeError):
            raise Failure('invalid-token-response') from None
        tokens = [line.split(':', 1)[1].strip() for line in headers.splitlines() if line.lower().startswith('x-subject-token:')]
        if len(tokens) != 1 or not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,8192}', tokens[0]):
            raise Failure('missing-or-invalid-token')
        secret_dir.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.campus-secrets-', dir=secret_dir.parent) as stage:
            stage = Path(stage)
            for name in NAMES:
                data, _ = request('GET', swift_url + '/campus-secrets/app/' + name, deadline,
                                  scratch_dir=state_dir, token=tokens[0], limit=4096)
                file = stage / name
                file.write_bytes(validate(name, data))
                file.chmod(0o444)
            deadline.remaining()
            stage.rename(secret_dir)
        state = dict(boot_id=boot_id(), started=started, deadline=deadline.end,
                     generation=str(time.monotonic_ns()))
        atomic_json(state_dir / 'secrets.json', state)
        return state


if __name__ == '__main__':
    cli(lambda: fetch(read_json('/etc/campuslink/bootstrap.json')))
