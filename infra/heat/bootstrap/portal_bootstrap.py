"""Bootstrap rieng cho VM portal cua issue 98. Khong in secret ra console."""
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from controls import IPTABLES, RULE, check_rule, checked
from fetch_secrets import endpoint, request
from runtime import Deadline, Failure, command, private_dir, read_json

ROOT = Path('/run/campuslink-portal-2411')
BOOT = Path('/etc/campuslink-portal-2411/boot.json')
IMAGE = r'ghcr\.io/dqh1215/campus-portal@sha256:[a-f0-9]{64}'
FILES = {
    'portal_db_url': 'PORTAL_DB_URL_FILE',
    'portal_secret_key': 'PORTAL_SECRET_KEY_FILE',
    'redis_servers': 'REDIS_SERVERS_FILE',
    'swift_app_cred': 'SWIFT_APP_CRED_FILE',
}


def settings(config):
    if not re.fullmatch(IMAGE, config['portal_image_ref']):
        raise Failure('portal-image-not-pinned')
    value = config['shlink_api_url'].rstrip('/')
    url = urlsplit(value)
    if (url.scheme not in ('http', 'https') or not url.hostname or url.username or
            url.password or url.path or url.query or url.fragment or url.hostname == 'localhost'):
        raise Failure('invalid-shlink-endpoint')
    try:
        address = ipaddress.ip_address(url.hostname)
    except ValueError:
        if url.scheme != 'https':
            raise Failure('shlink-http-requires-private-ip') from None
    else:
        if address.is_loopback or address.is_link_local or (url.scheme == 'http' and not address.is_private):
            raise Failure('invalid-shlink-address')
    if url.port == 0:
        raise Failure('invalid-shlink-port')
    keystone = endpoint(config['keystone_url'])
    swift = endpoint(config['swift_url'])
    if urlsplit(keystone).path != '/identity' or not re.fullmatch(r'/v1/AUTH_[a-zA-Z0-9]+', urlsplit(swift).path):
        raise Failure('invalid-identity-or-swift-path')
    return keystone, swift, value


def valid_secret(name, data):
    text = data.decode('utf-8').strip()
    if not text or '\0' in text:
        raise Failure('invalid-object-content')
    if name == 'swift_app_cred':
        valid = re.fullmatch(r'id=[a-fA-F0-9]{32}\r?\nsecret=[A-Za-z0-9_+/=-]{16,256}', text) is not None
    elif name == 'portal_secret_key':
        valid = re.fullmatch(r'[^\s]+', text) is not None and len(text) >= 16
    else:
        url = urlsplit(text)
        valid = url.hostname is not None and bool(url.password) and not any(c.isspace() for c in text)
        if name == 'portal_db_url':
            valid = valid and url.scheme == 'postgresql' and url.path == '/campus_portal'
        else:
            valid = valid and url.scheme in ('tcp', 'redis', 'rediss')
    if not valid:
        raise Failure('invalid-object-content')
    return (text + '\n').encode()


def fetch(config, state=ROOT):
    keystone, swift, _ = settings(config)
    private_dir(state)
    deadline = Deadline(time.monotonic() + 120)
    payload = json.dumps({'auth': {'identity': {'methods': ['application_credential'],
        'application_credential': {'id': config['credential_id'],
                                   'secret': config['credential_secret']}}}}).encode()
    body, headers = request('POST', keystone + '/v3/auth/tokens', deadline,
                            scratch_dir=state, payload=payload)
    tokens = [line.split(':', 1)[1].strip() for line in headers.splitlines()
              if line.lower().startswith('x-subject-token:')]
    if (not isinstance(json.loads(body).get('token'), dict) or len(tokens) != 1 or
            not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,8192}', tokens[0])):
        raise Failure('invalid-keystone-response')
    with tempfile.TemporaryDirectory(prefix='portal-secrets-', dir=state) as work:
        stage = Path(work)
        for name in FILES:
            data, _ = request('GET', f'{swift}/campus-secrets/app/{name}', deadline,
                              scratch_dir=state, token=tokens[0], limit=4096)
            path = stage / name
            path.touch(mode=0o600, exist_ok=False)
            path.write_bytes(valid_secret(name, data))
            os.chown(path, 0, 1002)
            path.chmod(0o440)
        deadline.remaining()
        for name in FILES:
            (stage / name).replace(state / name)
    return state


def docker_args(config, secret_dir):
    keystone, swift, shlink = settings(config)
    argv = ['docker', 'run', '--rm', '--name', 'campus-portal-2411', '--pull=never',
            '--network', 'bridge', '--publish', '8081:8081', '--user', '1002:1002',
            '--cap-drop=ALL', '--security-opt=no-new-privileges', '--log-driver=none']
    env = dict(ROLE='portal', PORTAL_PORT='8081', SHLINK_API_URL=shlink,
               QR_STORAGE='swift', SWIFT_CONTAINER_QR='campus-qr', OS_AUTH_URL=keystone,
               SWIFT_URL=swift, TIMEZONE='UTC')
    for name, variable in FILES.items():
        target = '/run/secrets/' + name
        argv += ['--mount', f'type=bind,src={secret_dir / name},dst={target},readonly']
        env[variable] = target
    for name, value in env.items():
        argv += ['--env', f'{name}={value}']
    return argv + [config['portal_image_ref']]


def guard_metadata():
    if command(IPTABLES + ['-C', 'DOCKER-USER'] + RULE).returncode:
        checked(IPTABLES + ['-I', 'DOCKER-USER', '1'] + RULE, command)
    check_rule(command)


def main():
    stage = 'guest'
    try:
        if os.geteuid() != 0 or checked(['cloud-id'], command).strip() != b'openstack':
            raise Failure('openstack-guest-required')
        stage = 'config'
        config = read_json(BOOT)
        settings(config)
        stage = 'metadata-guard'
        guard_metadata()
        stage = 'pull-image'
        checked(['docker', 'pull', '--platform', 'linux/amd64', config['portal_image_ref']],
                lambda argv: command(argv, timeout=240))
        stage = 'fetch-secrets'
        secrets = fetch(config)
        stage = 'start-portal'
        # Log raw cua app co the chua URI. Chi systemd exit va probe health duoc bao.
        print('Portal bootstrap OK; starting container', flush=True)
        status = subprocess.call(docker_args(config, secrets), stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        if status:
            raise Failure('container-failed')
    except (Failure, OSError, TypeError, KeyError, ValueError, AttributeError):
        print(f'Portal bootstrap FAIL: {stage}', flush=True)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
