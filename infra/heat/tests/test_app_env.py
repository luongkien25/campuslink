"""Env root HOT: credential chi doc noi bo, atomic0600/no-overwrite."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HEAT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HEAT))


class AppEnvTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HEAT / 'make_app_env.py').exists(), 'helper chua implement')
        spec = importlib.util.spec_from_file_location('make_app_env', HEAT / 'make_app_env.py')
        self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.base.chmod(0o700)
        self.cred = self.base / 'fake.cred'
        self.cred.write_text('id=' + 'a'*32 + '\nsecret=' + 'FAKE_ONLY_FOR_TEST_'*2 + '\n')
        self.cred.chmod(0o600)
        self.out = self.base / 'env.yaml'
        self.params = dict(app_image='2c43a06d-1db8-4c01-bd31-98803325d932',
            key_name='campus-tv2', app_network='18ecc898-663f-4440-9782-bdf1675ba5c9',
            app_subnet='59399337-e22b-4237-87dd-bf4ac035bcfa',
            app_security_group='b3eb3225-3e50-4c38-b43f-3823b6022d05')

    def test_creates_complete_root_env_private_and_preserves_existing(self):
        self.mod.make_env(self.cred, self.out, self.params)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)
        result = json.loads(self.out.read_text())['parameters']
        self.assertEqual(result['bootstrap_credential_id'], 'a'*32)
        self.assertEqual(result['az_b'], 'campus-az-b')
        self.assertEqual(result['readiness_timeout'], 180)
        self.assertEqual(result['diagnostic_security_groups'], [])
        before = self.out.read_bytes()
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(self.cred, self.out, self.params)
        self.assertEqual(self.out.read_bytes(), before)

    def test_rejects_unknown_fault_and_out_of_contract_inputs_before_publish(self):
        for extra in ({'unknown': 1}, {'app_flavor': 'campus.builder'}, {'az_b': 'nova'},
                      {'readiness_timeout': 300}, {'drain_seconds': -1}, {'app_image': 'ubuntu-noble-base'},
                      {'key_name': 'bad\nkey'}):
            with self.subTest(extra=extra), self.assertRaises((self.mod.Invalid, ValueError)):
                self.mod.make_env(self.cred, self.out, dict(self.params, **extra))
            self.assertFalse(self.out.exists())

    def test_rejects_public_credential_and_symlink_and_parent(self):
        self.cred.chmod(0o644)
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(self.cred, self.out, self.params)
        self.cred.chmod(0o600)
        link = self.base / 'link'; link.symlink_to(self.cred)
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(link, self.out, self.params)
        self.base.chmod(0o755)
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(self.cred, self.out, self.params)

    def test_telemetry_defaults_cannot_enable_unverified_evaluation_or_action(self):
        self.mod.make_env(self.cred, self.out, self.params)
        result = json.loads(self.out.read_text())['parameters']
        self.assertFalse(result['alarms_enabled'])
        self.assertFalse(result['scaling_actions_enabled'])
        self.assertEqual(result['cpu_rate_semantics'], 'unverified')

    def test_only_verified_shadow_or_explicit_action_transport_can_be_published(self):
        invalid = [dict(alarms_enabled=True), dict(scaling_actions_enabled=True),
                   dict(telemetry_project_id='bad'), dict(cpu_rate_semantics='guess'),
                   dict(telemetry_verified='true'), dict(scaling_action_transport='http://secret'),
                   dict(alarms_enabled=True, telemetry_verified=True, telemetry_project_id='a'*32,
                        cpu_rate_semantics='delta-ns', scaling_actions_enabled=True)]
        for extra in invalid:
            with self.subTest(extra=extra), self.assertRaises(self.mod.Invalid):
                self.mod.make_env(self.cred, self.out, dict(self.params, **extra))
            self.assertFalse(self.out.exists())
        ready = dict(alarms_enabled=True, telemetry_verified=True,
                     telemetry_project_id='a'*32, cpu_rate_semantics='delta-ns')
        self.mod.make_env(self.cred, self.out, dict(self.params, **ready))
        result = json.loads(self.out.read_text())['parameters']
        self.assertTrue(result['alarms_enabled'])
        self.assertFalse(result['scaling_actions_enabled'])


if __name__ == '__main__':
    unittest.main()
