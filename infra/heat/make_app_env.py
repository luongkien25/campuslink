"""Tao env root HOT tren A; tai dung parser credential G4, khong source shell."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from image.make_clone_env import Invalid, credential, private_parent

DEFAULTS = dict(app_flavor='campus.app', external_network='public', az_a='campus-az-a',
                az_b='campus-az-b', readiness_timeout=180, drain_seconds=5,
                metric_group_metadata='campuslink-app', diagnostic_security_groups=[],
                alarms_enabled=False, scaling_actions_enabled=False, telemetry_verified=False,
                telemetry_project_id='', cpu_rate_semantics='unverified', scaling_action_transport='unverified')
REQUIRED = {'app_image', 'key_name', 'app_network', 'app_subnet', 'app_security_group'}


def make_env(credential_path, output_path, root_params):
    if set(root_params) - (set(DEFAULTS) | REQUIRED) or REQUIRED - set(root_params):
        raise Invalid('invalid-root-parameters')
    params = dict(DEFAULTS, **root_params)
    for flag in ('alarms_enabled', 'scaling_actions_enabled', 'telemetry_verified'):
        if type(params[flag]) is not bool:
            raise Invalid('invalid-telemetry-flag')
    if (not isinstance(params['telemetry_project_id'], str)
            or not re.fullmatch(r'(|[a-f0-9]{32})', params['telemetry_project_id'])
            or params['cpu_rate_semantics'] not in ('unverified', 'delta-ns', 'ns-per-second')
            or params['scaling_action_transport'] not in ('unverified', 'native', 'signed')):
        raise Invalid('invalid-telemetry-contract')
    if params['alarms_enabled'] and (not params['telemetry_verified']
            or not params['telemetry_project_id'] or params['cpu_rate_semantics'] == 'unverified'):
        raise Invalid('telemetry-not-verified')
    if params['scaling_actions_enabled'] and (not params['alarms_enabled']
            or params['scaling_action_transport'] == 'unverified'):
        raise Invalid('action-transport-not-verified')
    for name in ('app_image', 'app_network', 'app_subnet', 'app_security_group'):
        uuid.UUID(params[name])
    if not isinstance(params['diagnostic_security_groups'], list):
        raise Invalid('invalid-diagnostic-groups')
    for group in params['diagnostic_security_groups']:
        uuid.UUID(group)
    for name in ('key_name', 'external_network'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', params[name]):
            raise Invalid('invalid-name')
    for key in ('app_flavor', 'az_a', 'az_b', 'readiness_timeout', 'metric_group_metadata'):
        if params[key] != DEFAULTS[key]:
            raise Invalid('out-of-contract')
    if type(params['drain_seconds']) not in (int, float) or not 5 <= params['drain_seconds'] <= 30:
        raise Invalid('invalid-drain')
    output_path = Path(output_path)
    private_parent(output_path)
    if os.path.lexists(output_path):
        raise Invalid('output-already-exists')
    values = credential(credential_path)
    params.update(bootstrap_credential_id=values['id'], bootstrap_credential_secret=values['secret'])
    fd, temp = tempfile.mkstemp(prefix='.app-env-', dir=output_path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'parameters': params}, stream)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.link(temp, output_path, follow_symlinks=False)
    except FileExistsError:
        raise Invalid('output-already-exists') from None
    finally:
        Path(temp).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Create private root Heat env; no secret output')
    parser.add_argument('--credential-file', type=Path, default=Path.home()/'.config/openstack/campus-boot.cred')
    parser.add_argument('--out', required=True, type=Path)
    for name in sorted(REQUIRED):
        parser.add_argument('--'+name.replace('_','-'), required=True)
    parser.add_argument('--diagnostic-sg',action='append',default=[])
    parser.add_argument('--alarms-enabled', action='store_true')
    parser.add_argument('--scaling-actions-enabled', action='store_true')
    parser.add_argument('--telemetry-verified', action='store_true')
    parser.add_argument('--telemetry-project-id', default='')
    parser.add_argument('--cpu-rate-semantics', choices=('unverified', 'delta-ns', 'ns-per-second'), default='unverified')
    parser.add_argument('--scaling-action-transport', choices=('unverified', 'native', 'signed'), default='unverified')
    args = parser.parse_args()
    try:
        telemetry_keys = ('alarms_enabled', 'scaling_actions_enabled', 'telemetry_verified',
                          'telemetry_project_id', 'cpu_rate_semantics', 'scaling_action_transport')
        make_env(args.credential_file, args.out, dict({k:getattr(args,k) for k in REQUIRED},
            **{k:getattr(args,k) for k in telemetry_keys}, diagnostic_security_groups=args.diagnostic_sg))
    except (Invalid, OSError, ValueError, TypeError, AttributeError):
        print('FAIL: private root env not created; check paths, modes and parameters')
        return 1
    print('OK: private root env created; values not printed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
