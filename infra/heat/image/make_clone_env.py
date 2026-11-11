"""Tao Heat env0600 tren A; chi nhan PATH credential, khong source shell."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid


class Invalid(Exception):
    pass


def private_parent(path):
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise Invalid('unsafe-parent')


def credential(path):
    path = Path(path)
    private_parent(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise Invalid('credential-unavailable') from None
    with os.fdopen(fd, 'r') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096:
            raise Invalid('unsafe-credential')
        lines = stream.read(4097).splitlines()
    values = {}
    for line in lines:
        key, sep, value = line.partition('=')
        if not sep or key not in ('id', 'secret') or key in values:
            raise Invalid('invalid-credential-format')
        # Khong eval/source va khong mo rong shell, ke ca file co duoc chmod600.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        values[key] = value
    if not re.fullmatch(r'[a-fA-F0-9]{32}', values.get('id', '')) or not re.fullmatch(r'[A-Za-z0-9_+/=-]{16,256}', values.get('secret', '')):
        raise Invalid('invalid-credential-format')
    return values


def make_env(credential_path, output_path, parameters):
    keys = {'image', 'flavor', 'network', 'subnet', 'key_name', 'security_groups', 'availability_zone'}
    if set(parameters) != keys or parameters['flavor'] != 'campus.app' or parameters['availability_zone'] not in ('campus-az-a', 'campus-az-b'):
        raise Invalid('invalid-clone-parameters')
    for key in ('image', 'network', 'subnet'):
        uuid.UUID(parameters[key])
    if not isinstance(parameters['security_groups'], list) or not parameters['security_groups']:
        raise Invalid('missing-security-groups')
    for group in parameters['security_groups']:
        uuid.UUID(group)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', parameters['key_name']):
        raise Invalid('invalid-keypair')
    output_path = Path(output_path)
    private_parent(output_path)
    if os.path.lexists(output_path):
        raise Invalid('output-already-exists')
    values = credential(credential_path)
    result = {'parameters': dict(parameters, bootstrap_credential_id=values['id'], bootstrap_credential_secret=values['secret'])}
    fd, temp = tempfile.mkstemp(prefix='.clone-env-', dir=output_path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(result, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        # Link publish khong ghi de output vua duoc tao boi process khac.
        os.link(temp, output_path, follow_symlinks=False)
    except FileExistsError:
        raise Invalid('output-already-exists') from None
    finally:
        Path(temp).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Create private Heat clone env on A; never print credential')
    parser.add_argument('--credential-file', type=Path, default=Path.home() / '.config/openstack/campus-boot.cred')
    parser.add_argument('--out', type=Path, required=True)
    for name in ('image', 'network', 'subnet', 'key-name', 'app-sg', 'ssh-sg'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--az', choices=('campus-az-a', 'campus-az-b'), required=True)
    args = parser.parse_args()
    try:
        make_env(args.credential_file, args.out, dict(image=args.image, flavor='campus.app', network=args.network,
                 subnet=args.subnet, key_name=args.key_name, security_groups=[args.app_sg, args.ssh_sg], availability_zone=args.az))
    except (Invalid, OSError, ValueError, TypeError):
        print('FAIL: clone env not created (check private file, parameters and output path)')
        return 1
    print('OK: private clone env created; values not printed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
