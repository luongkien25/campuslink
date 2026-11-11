"""Cac primitive runtime; khong ghi gia tri bi mat vao log/argv."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

IMAGE = 'shlinkio/shlink@sha256:68a722f7677008a50ccf3a9e570966bc37d7627fe6a870b86be28c5dcf9085ee'
SECRETS = Path('/run/secrets')
STATE = Path('/run/campuslink')


class Failure(Exception):
    pass


class Deadline:
    def __init__(self, end):
        self.end = end

    def remaining(self, cap=5):
        left = min(cap, self.end - time.monotonic())
        if left <= 0:
            raise Failure('deadline')
        return left


def command(argv, *, timeout=5, input=None):
    try:
        return subprocess.run(argv, input=input, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Failure('command-unavailable-or-timeout') from None


def private_dir(path):
    path = Path(path)
    if path.is_symlink():
        raise Failure('unsafe-directory')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise Failure('unsafe-directory')


def atomic_json(path, value):
    path = Path(path)
    private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def read_json(path):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError:
        raise Failure('missing-config-or-state') from None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise Failure('unsafe-config-or-state')
    if info.st_size > 16384:
        raise Failure('oversize-config-or-state')
    try:
        return json.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise Failure('invalid-config-or-state') from None


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def active_state(state_dir=STATE):
    state = read_json(Path(state_dir) / 'secrets.json')
    if state.get('boot_id') != boot_id():
        raise Failure('stale-boot')
    Deadline(state['deadline']).remaining()
    return state


def require_guest():
    if os.geteuid() != 0:
        raise Failure('guest-root-required')
    marker = Path('/etc/campuslink/image-role')
    if not marker.is_file() or marker.read_text().strip() != 'campuslink-app-v1':
        raise Failure('app-guest-required')
    result = command(['cloud-id'])
    if result.returncode or result.stdout.strip() != b'openstack':
        raise Failure('openstack-guest-required')


def cli(action):
    try:
        require_guest()
        action()
        print('OK')
    except (Failure, OSError, ValueError, KeyError, TypeError):
        # Khong in exception: thu vien/remote co the kem secret trong message.
        print('FAIL: runtime precondition or operation failed', flush=True)
        raise SystemExit(1)
