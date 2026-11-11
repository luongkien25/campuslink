import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class DockerFixture:
    def __init__(self):
        self.calls = []
        self.rule = False
        self.backend = 'iptables'
        self.version = '28.0.0'
        self.image = True
        self.forward = True
        self.early_accept = False

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        code, out = 0, b''
        if argv[:2] == ['docker', 'version']:
            out = self.version.encode()
        elif argv[:3] == ['docker', 'image', 'inspect']:
            code = 0 if self.image else 1
        elif argv[:3] == ['docker', 'container', 'inspect']:
            code = 1
        elif argv[:3] == ['ip', '-j', 'route']:
            out = b'[{"prefsrc":"10.20.0.11"}]'
        elif argv[:3] == ['iptables', '-w', '5']:
            if '-S' in argv:
                chain = argv[-1]
                if chain == 'FORWARD':
                    out = b'-P FORWARD DROP\n-A FORWARD -j DOCKER-USER\n'
                else:
                    out = b'-N DOCKER-USER\n'
                    if self.early_accept:
                        out += b'-A DOCKER-USER -j ACCEPT\n'
                    if self.rule:
                        out += b'-A DOCKER-USER -d 169.254.169.254/32 -j DROP\n'
                    out += b'-A DOCKER-USER -j RETURN\n'
            elif '-C' in argv and 'FORWARD' in argv:
                code = 0 if self.forward else 1
            elif '-C' in argv:
                code = 0 if self.rule else 1
            elif '-I' in argv:
                self.rule = True
        return subprocess.CompletedProcess(argv, code, out, b'')


class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'controls.py').exists(), 'controls chua implement')
        import controls
        from runtime import atomic_json, boot_id
        self.mod = controls
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.secrets = self.root / 'secrets'
        self.secrets.mkdir(mode=0o700)
        for name in ('db_password', 'redis_servers'):
            file = self.secrets / name
            file.write_text('fixture')
            file.chmod(0o444)
        atomic_json(self.state / 'secrets.json', dict(boot_id=boot_id(), started=time.monotonic(),
                    deadline=time.monotonic() + 180, generation='test-1'))
        self.daemon = self.root / 'daemon.json'
        self.daemon.write_text('{}')
        self.executor = DockerFixture()
        self.instance_data = self.root / 'instance-data.json'
        self.instance_data.write_text('{"v1":{"instance_id":"12345678-1234-1234-1234-123456789abc"}}')

    def guard(self):
        return self.mod.guard(self.state, self.daemon, run=self.executor)

    def start(self):
        return self.mod.start(self.state, self.secrets, run=self.executor, instance_data=self.instance_data)

    def test_guard_idempotent_and_start_no_pull_or_restart(self):
        self.guard()
        self.guard()
        self.assertEqual(sum('-I' in c for c in self.executor.calls), 1)
        argv = self.start()
        self.assertEqual(argv[:2], ['docker', 'run'])
        self.assertIn('--restart=no', argv)
        self.assertIn('--pull=never', argv)
        self.assertIn('--network=bridge', argv)
        self.assertEqual(sum('readonly' in x for x in argv), 2)
        self.assertNotIn('fixture', repr(argv))
        self.assertIn('--label=campuslink.guest_uuid=12345678-1234-1234-1234-123456789abc', argv)
        self.assertIn('--label=campuslink.guest_ip=10.20.0.11', argv)

    def test_invalid_guest_identity_blocks_start(self):
        self.guard()
        self.instance_data.write_text('{"v1":{"instance_id":"not-a-uuid"}}')
        with self.assertRaises(self.mod.Failure):
            self.start()

    def test_earlier_accept_cannot_bypass_guard(self):
        self.guard()
        self.executor.early_accept = True
        with self.assertRaises(self.mod.Failure):
            self.start()

    def test_guard_failure_prevents_app_start(self):
        for backend in ('nftables', 'broken'):
            self.daemon.write_text(json.dumps({'firewall-backend': backend}))
            with self.assertRaises(self.mod.Failure):
                self.guard()
            with self.assertRaises(self.mod.Failure):
                self.start()
        self.assertFalse(any(c[:2] == ['docker', 'run'] for c in self.executor.calls))

    def test_docker29_requires_explicit_iptables_and_forward_hook(self):
        self.executor.version = '29.0.0'
        with self.assertRaises(self.mod.Failure):
            self.guard()
        self.daemon.write_text('{"firewall-backend":"iptables"}')
        self.executor.forward = False
        with self.assertRaises(self.mod.Failure):
            self.guard()
        self.executor.forward = True
        self.guard()

    def test_missing_image_secret_or_removed_rule_blocks_start(self):
        self.guard()
        self.executor.image = False
        with self.assertRaises(self.mod.Failure):
            self.start()
        self.executor.image = True
        self.executor.rule = False
        with self.assertRaises(self.mod.Failure):
            self.start()
        self.executor.rule = True
        (self.secrets / 'db_password').chmod(0o644)
        with self.assertRaises(self.mod.Failure):
            self.start()
        self.assertFalse(any(c[:2] == ['docker', 'run'] for c in self.executor.calls))


if __name__ == '__main__':
    unittest.main()
