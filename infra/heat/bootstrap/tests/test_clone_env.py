from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / 'image'))


class CloneEnvTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT.parent / 'image' / 'make_clone_env.py').is_file(), 'helper chua implement')
        import make_clone_env
        self.mod = make_clone_env
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.cred = self.dir / 'campus-boot.cred'
        self.cred.write_text('id=' + 'a' * 32 + '\nsecret=fake-secret-1234567890\n')
        self.cred.chmod(0o600)
        self.out = self.dir / 'clone-env.json'
        self.params = dict(image='12345678-1234-1234-1234-123456789abc', flavor='campus.app',
            network='12345678-1234-1234-1234-123456789abc', subnet='12345678-1234-1234-1234-123456789abc',
            key_name='campus-tv2', security_groups=['12345678-1234-1234-1234-123456789abc'], availability_zone='campus-az-a')

    def test_creates_private_json_heat_environment(self):
        self.mod.make_env(self.cred, self.out, self.params)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)
        data = json.loads(self.out.read_text())['parameters']
        self.assertEqual(data['bootstrap_credential_id'], 'a' * 32)
        self.assertEqual(data['bootstrap_credential_secret'], 'fake-secret-1234567890')
        self.assertEqual(data['security_groups'], self.params['security_groups'])

    def test_rejects_executable_or_ambiguous_credential_file(self):
        for text in ['id=' + 'a' * 32 + '\nsecret=$(touch injected)\n',
                     'id=' + 'a' * 32 + '\nid=' + 'b' * 32 + '\nsecret=fake-secret-1234567890\n',
                     'id=' + 'a' * 32 + '\n', 'extra=oops\nid=' + 'a' * 32 + '\nsecret=fake-secret-1234567890\n']:
            self.cred.write_text(text)
            with self.assertRaises(self.mod.Invalid):
                self.mod.make_env(self.cred, self.out, self.params)
            self.assertFalse(self.out.exists())
        self.assertFalse((self.dir / 'injected').exists())

    def test_rejects_unsafe_modes_and_symlink(self):
        self.cred.chmod(0o644)
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(self.cred, self.out, self.params)
        self.cred.chmod(0o600)
        link = self.dir / 'link'
        link.symlink_to(self.cred)
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(link, self.out, self.params)
        self.dir.chmod(0o755)
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(self.cred, self.out, self.params)

    def test_never_overwrites_existing_output_or_follows_output_symlink(self):
        self.out.write_text('keep')
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(self.cred, self.out, self.params)
        self.assertEqual(self.out.read_text(), 'keep')
        self.out.unlink()
        self.out.symlink_to(self.cred)
        with self.assertRaises(self.mod.Invalid):
            self.mod.make_env(self.cred, self.out, self.params)
        self.assertTrue(self.cred.read_text().startswith('id='))


if __name__ == '__main__':
    unittest.main()
