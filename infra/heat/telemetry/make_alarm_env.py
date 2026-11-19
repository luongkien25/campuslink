"""Tao env rieng cho alarm; targets chi doc tu file private, khong in gia tri."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import urlsplit

KEYS = {'project_id', 'group', 'high_threshold', 'low_threshold', 'evaluation_enabled',
        'actions_enabled', 'telemetry_verified', 'transport_verified', 'transport'}


def private_parent(path):
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('unsafe-parent')


def private_json(path):
    path = Path(path)
    private_parent(path)
    # Nonblock de file dac biet khong lam helper treo truoc khi kiem fstat.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise ValueError('input-unavailable') from None
    with os.fdopen(fd, 'r') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 16384):
            raise ValueError('unsafe-input')
        return json.loads(stream.read(16385))


def make_env(action_file, output_path, params):
    if not isinstance(params, dict) or set(params) != KEYS:
        raise ValueError('invalid-parameters')
    for key in ('evaluation_enabled', 'actions_enabled', 'telemetry_verified', 'transport_verified'):
        if type(params[key]) is not bool:
            raise ValueError('invalid-flag')
    if (not isinstance(params['project_id'], str) or not re.fullmatch('[a-f0-9]{32}', params['project_id'])
            or params['group'] != 'campuslink-app'
            or type(params['high_threshold']) not in (int, float) or params['high_threshold'] != 36000000000
            or type(params['low_threshold']) not in (int, float) or params['low_threshold'] != 15000000000
            or params['transport'] not in ('unverified', 'native', 'signed')):
        raise ValueError('invalid-contract')
    if params['evaluation_enabled'] and not params['telemetry_verified']:
        raise ValueError('telemetry-not-verified')
    if params['actions_enabled'] and (not params['evaluation_enabled']
            or not params['transport_verified'] or params['transport'] == 'unverified'):
        raise ValueError('transport-not-verified')
    output_path = Path(output_path)
    private_parent(output_path)
    if os.path.lexists(output_path):
        raise ValueError('output-already-exists')
    targets = dict(high_action='', low_action='')
    if params['actions_enabled']:
        targets = private_json(action_file)
        if not isinstance(targets, dict) or set(targets) != {'high_action', 'low_action'}:
            raise ValueError('invalid-targets')
        for value in targets.values():
            if (not isinstance(value, str) or not value.isascii() or len(value) > 8192
                    or any(ord(c) <= 32 or ord(c) == 127 for c in value)):
                raise ValueError('invalid-targets')
            parsed = urlsplit(value)
            if not parsed.scheme or not parsed.hostname or not parsed.path or parsed.fragment:
                raise ValueError('invalid-targets')
        if targets['high_action'] == targets['low_action']:
            raise ValueError('duplicate-targets')
    # Le flag la xac nhan van hanh, khong tu xac minh notifier/cloud.
    parameters = {k: params[k] for k in ('project_id', 'group', 'high_threshold', 'low_threshold',
                                        'evaluation_enabled', 'actions_enabled')}
    parameters.update(targets)
    fd, temp = tempfile.mkstemp(prefix='.alarm-env-', dir=output_path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'parameters': parameters}, stream)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.link(temp, output_path, follow_symlinks=False)
    finally:
        Path(temp).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Create private standalone alarm env; no secret output')
    parser.add_argument('--action-file', type=Path, required=True)
    parser.add_argument('--params-file', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        make_env(args.action_file, args.out, private_json(args.params_file))
    except (ValueError, TypeError, KeyError, OSError):
        print('FAIL: alarm env not created; check private inputs, flags and output')
        return 1
    print('OK: private alarm env created; values not printed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
