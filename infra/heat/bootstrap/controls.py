"""Guard va cac dieu kien truoc docker run; chi CLI duoc chay trong guest."""
import json
import ipaddress
import os
from pathlib import Path
import stat
import uuid

from runtime import (IMAGE, SECRETS, STATE, Failure, active_state, atomic_json,
                     command, private_dir, read_json)

RULE = ['-d', '169.254.169.254/32', '-j', 'DROP']
IPTABLES = ['iptables', '-w', '5']


def checked(argv, run):
    result = run(argv)
    if result.returncode:
        raise Failure('runtime-command-failed')
    return result.stdout


def check_rule(run):
    checked(IPTABLES + ['-C', 'FORWARD', '-j', 'DOCKER-USER'], run)
    checked(IPTABLES + ['-C', 'DOCKER-USER'] + RULE, run)
    for chain, expected in [('FORWARD', '-A FORWARD -j DOCKER-USER'),
                            ('DOCKER-USER', '-A DOCKER-USER -d 169.254.169.254/32 -j DROP')]:
        rules = [line for line in checked(IPTABLES + ['-S', chain], run).decode().splitlines() if line.startswith('-A ')]
        if not rules or rules[0] != expected:
            raise Failure('metadata-rule-can-be-bypassed')


def guard(state_dir=STATE, daemon_path=Path('/etc/docker/daemon.json'), *, run=command):
    state_dir = Path(state_dir)
    (state_dir / 'guard.json').unlink(missing_ok=True)
    state = active_state(state_dir)
    major = int(checked(['docker', 'version', '--format', '{{.Server.Version}}'], run).decode().split('.')[0])
    config = json.loads(Path(daemon_path).read_text()) if Path(daemon_path).exists() else {}
    backend = config.get('firewall-backend')
    if backend not in ('iptables', None) or (major >= 29 and backend != 'iptables') or config.get('iptables') is False:
        raise Failure('unsupported-docker-firewall')
    checked(IPTABLES + ['-S', 'DOCKER-USER'], run)
    checked(IPTABLES + ['-C', 'FORWARD', '-j', 'DOCKER-USER'], run)
    if run(IPTABLES + ['-C', 'DOCKER-USER'] + RULE).returncode:
        checked(IPTABLES + ['-I', 'DOCKER-USER', '1'] + RULE, run)
    check_rule(run)
    active_state(state_dir)
    atomic_json(state_dir / 'guard.json', state)


def guest_identity(instance_data, run):
    try:
        data = json.loads(Path(instance_data).read_text())
        guest_uuid = str(uuid.UUID(data['v1']['instance_id']))
        route = json.loads(checked(['ip', '-j', 'route', 'get', '10.20.0.10'], run))
        guest_ip = str(ipaddress.IPv4Address(route[0]['prefsrc']))
        if ipaddress.IPv4Address(guest_ip) not in ipaddress.IPv4Network('10.20.0.0/24'):
            raise Failure('unexpected-guest-ip')
        return guest_uuid, guest_ip
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise Failure('missing-or-invalid-guest-identity') from None


def start(state_dir=STATE, secret_dir=SECRETS, *, run=command,
          instance_data=Path('/run/cloud-init/instance-data.json')):
    state = active_state(state_dir)
    if read_json(Path(state_dir) / 'guard.json') != state:
        raise Failure('stale-guard')
    private_dir(secret_dir)
    for name in ('db_password', 'redis_servers'):
        info = (Path(secret_dir) / name).lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o444:
            raise Failure('unsafe-secret-file')
    check_rule(run)
    checked(['docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'], run)
    if run(['docker', 'container', 'inspect', 'shlink', '--format', '{{.Id}}']).returncode == 0:
        raise Failure('existing-container-requires-inspection')
    guest_uuid, guest_ip = guest_identity(instance_data, run)
    argv = ['docker', 'run', '--rm', '--name', 'shlink', '--restart=no', '--pull=never',
            '--network=bridge', '--label=campuslink.runtime=app-v1',
            '--label=campuslink.guest_uuid=' + guest_uuid, '--label=campuslink.guest_ip=' + guest_ip,
            '--log-driver=json-file', '--log-opt=max-size=10m', '--log-opt=max-file=3',
            '--log-opt=labels=campuslink.guest_uuid,campuslink.guest_ip',
            '--publish=8080:8080', '--env-file=/opt/campuslink/shlink.env']
    for name in ('db_password', 'redis_servers'):
        argv += ['--mount', 'type=bind,src=' + str(Path(secret_dir) / name) + ',dst=/run/secrets/' + name + ',readonly']
    return argv + [IMAGE]
