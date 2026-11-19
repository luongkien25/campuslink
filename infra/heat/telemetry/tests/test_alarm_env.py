"""Kiem file env that; targets gia, khong goi OpenStack."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
TARGETS = {'high_action': 'https://heat.invalid/high?signature=FAKE_HIGH',
           'low_action': 'https://heat.invalid/low?signature=FAKE_LOW'}
PARAMS = dict(project_id='a'*32, group='campuslink-app', high_threshold=36000000000,
              low_threshold=15000000000, evaluation_enabled=False, actions_enabled=False,
              telemetry_verified=False, transport_verified=False, transport='unverified')


class AlarmEnvTests(unittest.TestCase):
    def setUp(self):
        path = BASE/'make_alarm_env.py'
        self.assertTrue(path.exists(), 'standalone alarm env helper not implemented')
        spec = importlib.util.spec_from_file_location('alarm_env', path)
        self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name); self.folder.chmod(0o700)
        self.source = self.folder/'targets.json'
        self.source.write_text(json.dumps(TARGETS)); self.source.chmod(0o600)
        self.out = self.folder/'env.json'

    def params(self, **kwargs):
        return dict(PARAMS, **kwargs)

    def active(self, **kwargs):
        return self.params(evaluation_enabled=True, actions_enabled=True,
                           telemetry_verified=True, transport_verified=True,
                           transport='signed', **kwargs)

    def test_disabled_does_not_read_targets(self):
        self.mod.make_env(self.folder/'missing', self.out, PARAMS)
        result = json.loads(self.out.read_text())['parameters']
        self.assertFalse(result['evaluation_enabled'])
        self.assertEqual((result['high_action'], result['low_action']), ('', ''))
        self.assertNotIn('transport_verified', result)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)

    def test_shadow_evaluation_requires_telemetry_but_not_targets(self):
        self.mod.make_env(self.folder/'missing', self.out,
                          self.params(evaluation_enabled=True, telemetry_verified=True))
        result = json.loads(self.out.read_text())['parameters']
        self.assertTrue(result['evaluation_enabled'])
        self.assertEqual(result['high_action'], '')

    def test_high_low_mapping_is_preserved_without_bootstrap_credential(self):
        self.mod.make_env(self.source, self.out, self.active())
        result = json.loads(self.out.read_text())['parameters']
        self.assertEqual(result['high_action'], TARGETS['high_action'])
        self.assertEqual(result['low_action'], TARGETS['low_action'])
        self.assertFalse(any('credential' in k or 'token' in k for k in result))

    def test_requires_evaluation_telemetry_and_transport_before_actions(self):
        for key, value in [('evaluation_enabled', False), ('telemetry_verified', False),
                           ('transport_verified', False), ('transport', 'unverified')]:
            with self.subTest(key=key):
                params = self.active(); params[key] = value
                with self.assertRaises(ValueError):
                    self.mod.make_env(self.source, self.out, params)
                self.assertFalse(self.out.exists())

    def test_rejects_wrong_project_units_flags_and_unknown_parameters(self):
        for key, value in [('project_id', 'wrong'), ('high_threshold', 600000000),
                           ('low_threshold', 250000000), ('group', 'other'),
                           ('evaluation_enabled', 'false'), ('extra', True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.mod.make_env(self.source, self.out, self.params(**{key: value}))

    def test_requires_both_distinct_absolute_targets_without_control_characters(self):
        for value in [{'high_action': TARGETS['high_action']},
                      dict(TARGETS, low_action=TARGETS['high_action']),
                      dict(TARGETS, low_action='relative/path'),
                      dict(TARGETS, low_action='https://heat.invalid/\nsecret'),
                      dict(TARGETS, unexpected='secret')]:
            self.source.write_text(json.dumps(value))
            with self.subTest(value=list(value)), self.assertRaises(ValueError):
                self.mod.make_env(self.source, self.out, self.active())
            self.assertFalse(self.out.exists())

    def test_rejects_public_source_symlink_directory_and_oversized_file(self):
        self.source.chmod(0o644)
        with self.assertRaises(ValueError): self.mod.make_env(self.source, self.out, self.active())
        self.source.chmod(0o600)
        link = self.folder/'link'; link.symlink_to(self.source)
        with self.assertRaises(ValueError): self.mod.make_env(link, self.out, self.active())
        with self.assertRaises(ValueError): self.mod.make_env(self.folder, self.out, self.active())
        self.source.write_text('X'*20000)
        with self.assertRaises(ValueError): self.mod.make_env(self.source, self.out, self.active())

    def test_rejects_public_or_symlink_parent_and_existing_output(self):
        self.out.write_text('preserve')
        with self.assertRaises(ValueError): self.mod.make_env(self.source, self.out, self.active())
        self.assertEqual(self.out.read_text(), 'preserve')
        self.out.unlink(); self.out.symlink_to(self.folder/'absent')
        with self.assertRaises(ValueError): self.mod.make_env(self.source, self.out, PARAMS)
        self.out.unlink(); self.folder.chmod(0o755)
        with self.assertRaises(ValueError): self.mod.make_env(self.source, self.out, PARAMS)
        self.folder.chmod(0o700)
        link = self.folder/'alias'; link.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(ValueError): self.mod.make_env(self.source, link/'out', PARAMS)

    def test_cli_does_not_echo_private_input_or_bad_json(self):
        self.source.write_text('{"high_action":"FAKE_PRIVATE_SENTINEL"')
        params = self.folder/'params.json'; params.write_text(json.dumps(self.active())); params.chmod(0o600)
        result = subprocess.run([sys.executable, '-B', str(BASE/'make_alarm_env.py'),
                                 '--action-file', str(self.source), '--params-file', str(params),
                                 '--out', str(self.out)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('FAKE_PRIVATE_SENTINEL', result.stdout+result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(self.out.exists())


if __name__ == '__main__': unittest.main()
