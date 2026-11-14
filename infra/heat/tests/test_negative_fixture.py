"""Fault template chi trong ban sao thu nghiem, khong sua root production."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import yaml

HEAT = Path(__file__).resolve().parents[1]


class NegativeFixtureTests(unittest.TestCase):
    def test_copies_files_and_faults_only_selected_unit_without_mutating_source(self):
        path = HEAT / 'tests/fixtures/make_negative.py'
        self.assertTrue(path.exists(), 'negative builder chua implement')
        spec = importlib.util.spec_from_file_location('make_negative', path)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        before = (HEAT/'root.yaml').read_bytes()
        for side in ('a','b'):
            with tempfile.TemporaryDirectory() as temp:
                dest = Path(temp)/'fixture'
                mod.build(dest, side)
                root = yaml.safe_load((dest/'root.yaml').read_text())
                self.assertNotIn('cpu_alarms', root['resources'])
                group = 'campuslink-tv2-negative-'+side
                self.assertEqual(root['resources']['app_a']['properties']['metric_group_metadata'], group)
                self.assertEqual(root['resources']['asg_b']['properties']['resource']['properties']['metric_group_metadata'], group)
                unit = yaml.safe_load((dest/'app-unit.yaml').read_text())
                self.assertEqual(unit['parameters']['metric_group_metadata']['default'], group)
                self.assertEqual(unit['parameters']['metric_group_metadata']['constraints'], [{'allowed_values': [group]}])
                a = root['resources']['app_a']['properties']['app_env']
                b = root['resources']['asg_b']['properties']['resource']['properties']['app_env']
                bad, good = (a,b) if side=='a' else (b,a)
                self.assertIn('DB_HOST=127.0.0.1', bad)
                self.assertNotIn('DB_HOST=127.0.0.1', good)
                for template in ('root.yaml','app-unit.yaml'):
                    text=(dest/template).read_text()
                    self.assertNotIn('../../app/',text)
                self.assertTrue((dest/'bootstrap/signal_ready.py').exists())
                with self.assertRaises(FileExistsError):
                    mod.build(dest, side)
        self.assertEqual((HEAT/'root.yaml').read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
