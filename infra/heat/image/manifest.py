"""Manifest tai lap khong secret; Glance facts se duoc bo sung tu output that."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def output(argv):
    return subprocess.check_output(argv, text=True).strip()


def manifest(repo, source_commit):
    repo = Path(repo)
    paths = sorted((repo / 'infra/heat/bootstrap').glob('*.py'))
    paths += sorted((repo / 'infra/heat/bootstrap').glob('*.sh'))
    paths += sorted((repo / 'infra/heat/bootstrap/systemd').rglob('*.service'))
    paths += sorted((repo / 'infra/heat/bootstrap/systemd').rglob('*.conf'))
    paths += [repo / 'app/shlink.env.example', repo / 'app/smoke/redis-probe.sh']
    return dict(status='BUILDER_ONLY_NOT_CLONE_VALIDATED', created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_commit=source_commit,
        source_attestation='archive phai tao tu commit sach; doi chieu files SHA-256',
        base_image_id='b915f809-b352-4d03-a14a-ec9c294e85d8',
        base_checksum='04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94',
        kernel=output(['uname', '-r']),
        packages=output(['dpkg-query', '-W', '-f=${Package}=${Version}\n', 'docker.io', 'curl', 'python3', 'redis-tools', 'iptables']),
        shlink_index_digest='sha256:68a722f7677008a50ccf3a9e570966bc37d7627fe6a870b86be28c5dcf9085ee',
        expected_shlink_amd64_digest='sha256:9083dc4ba2b682c43e1a477b69ef451738253fc8ad680db072663ea68530a973',
        docker_version=output(['docker', 'version', '--format', '{{.Server.Version}}']),
        cached_image=json.loads(output(['docker', 'image', 'inspect', 'shlinkio/shlink@sha256:68a722f7677008a50ccf3a9e570966bc37d7627fe6a870b86be28c5dcf9085ee', '--format', '{{json .}}'])),
        files={str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        glance=dict(id=None, min_disk=None, min_ram=None, virtual_size=None, size=None), clone_a=None, clone_b=None)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(manifest(sys.argv[1], sys.argv[3]), indent=2) + '\n')
