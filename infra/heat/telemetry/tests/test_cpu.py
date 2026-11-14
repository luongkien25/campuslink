"""Fixture CPU gia: bat loi don vi, tap VM va cua so; khong phai evidence cloud."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[1]
A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
C = '33333333-3333-4333-8333-333333333333'
PROJECT = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
NOW = datetime(2026, 11, 14, 12, 8, tzinfo=timezone.utc)


def fixture(values=(36e9, 15e9)):
    resources = []
    for ident, delta in zip((A, B, C), values):
        rows = []
        for minute in range(7):
            stamp = (NOW - timedelta(minutes=8-minute)).isoformat()
            rows.append(dict(timestamp=stamp, granularity_seconds=60,
                             aggregation='mean', value=1e12+minute*delta))
            if minute:
                rows.append(dict(timestamp=stamp, granularity_seconds=60,
                                 aggregation='rate:mean', value=delta))
        resources.append(dict(uuid=ident, vcpus=1, group='campuslink-app',
                              project_id=PROJECT, ended_at=None, deleted_at=None,
                              metric_id=ident, unit='ns', archive_policy={
                                  'name': 'fixture', 'aggregation_methods': ['mean', 'rate:mean'],
                                  'definition': [{'granularity': 60, 'points': 60, 'timespan': 3600}]}, rows=rows))
    return dict(schema_version=1, collected_at_utc=NOW.isoformat(), project_id=PROJECT,
                query={'and': [{'=': {'server_group': 'campuslink-app'}},
                               {'=': {'project_id': PROJECT}}, {'=': {'ended_at': None}},
                               {'=': {'deleted_at': None}}]},
                resources=resources)


class CpuTests(unittest.TestCase):
    def setUp(self):
        path = BASE/'analyze_cpu.py'
        self.assertTrue(path.exists(), 'analyzer chua implement')
        spec = importlib.util.spec_from_file_location('analyze_cpu', path)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def analyze(self, snapshot=None, expected=(A, B), semantics='delta-ns'):
        return self.mod.analyze(snapshot or fixture(), expected, now=NOW,
                                max_age_seconds=120, rate_semantics=semantics)

    def test_literal_cpu_conversion_and_mean_not_sum_for_two_and_three_vms(self):
        report = self.analyze()
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['instances'][A]['cpu_percent'], [60.0]*6)
        self.assertEqual(report['instances'][B]['cpu_percent'], [25.0]*6)
        self.assertEqual(report['group_cpu_percent'], [42.5]*6)
        report = self.analyze(fixture((36e9, 15e9, 6e9)), (A, B, C))
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['group_cpu_percent'], [31.666667]*6)
        self.assertEqual(report['instances'][C]['cpu_percent'], [10.0]*6)
        data = fixture(); data['resources'][0]['vcpus'] = 2
        self.assertEqual(self.analyze(data)['instances'][A]['cpu_percent'], [30.0]*6)

    def test_rate_units_must_match_raw_counter_and_explicit_semantics(self):
        data = fixture()
        self.assertFalse(self.analyze(data, semantics='ns-per-second')['passed'])
        for resource in data['resources']:
            for row in resource['rows']:
                if row['aggregation'] == 'rate:mean':
                    row['value'] /= 60
        self.assertTrue(self.analyze(data, semantics='ns-per-second')['passed'])
        with self.assertRaises(ValueError):
            self.analyze(semantics='guess')

    def test_missing_stale_future_duplicate_out_of_order_or_gapped_points_fail_closed(self):
        cases = []
        data = fixture(); data['resources'][0]['rows'].pop(); cases.append(data)
        data = fixture(); data['resources'][0]['rows'].append(deepcopy(data['resources'][0]['rows'][-1])); cases.append(data)
        data = fixture(); data['resources'][0]['rows'].reverse(); cases.append(data)
        data = fixture(); data['resources'][0]['rows'][0]['value'] = float('nan'); cases.append(data)
        data = fixture(); data['resources'][0]['rows'][0]['timestamp'] = '2026-11-14T12:00:00'; cases.append(data)
        data = fixture(); data['resources'][0]['rows'][1]['value'] = -1; cases.append(data)
        data = fixture(); data['resources'][0]['rows'][1]['timestamp'] = '2026-11-14T12:08:00Z'; cases.append(data)
        data = fixture(); data['resources'][0]['rows'][2]['granularity_seconds'] = 300; cases.append(data)
        data = fixture(); data['resources'][0]['rows'][0]['value'] = 2e12; cases.append(data)
        for data in cases:
            with self.subTest(data=data):
                result = self.analyze(data)
                self.assertFalse(result['passed'])
                self.assertEqual(result['group_cpu_percent'], [])
        self.assertFalse(self.mod.analyze(fixture(), (A, B), now=NOW+timedelta(minutes=10),
            max_age_seconds=120, rate_semantics='delta-ns')['passed'])

    def test_missing_extra_duplicate_wrong_project_ended_or_non_app_resources_fail(self):
        cases = []
        data = fixture(); data['resources'].pop(); cases.append(data)
        cases.append(fixture((36e9, 15e9, 6e9)))
        data = fixture(); data['resources'].append(deepcopy(data['resources'][0])); cases.append(data)
        for key, bad in [('group', 'campus-db'), ('project_id', 'b'*32),
                         ('ended_at', '2026-11-14T11:00:00Z'), ('deleted_at', '2026-11-14T11:00:00Z'), ('vcpus', 0),
                         ('vcpus', True), ('unit', 'percent')]:
            data = fixture(); data['resources'][0][key] = bad; cases.append(data)
        for data in cases:
            with self.subTest(data=data):
                self.assertFalse(self.analyze(data)['passed'])

    def test_archive_policy_requires_60_seconds_and_both_aggregations(self):
        for change in ('methods', 'granularity'):
            data = fixture(); policy = data['resources'][0]['archive_policy']
            if change == 'methods':
                policy['aggregation_methods'] = ['mean']
            else:
                policy['definition'][0]['granularity'] = 300
            self.assertFalse(self.analyze(data)['passed'])

    def test_thresholds_require_strict_and_complete_windows(self):
        self.assertEqual(self.mod.window_state([61, 65], 'high'), 'alarm')
        self.assertEqual(self.mod.window_state([61, 60], 'high'), 'ok')
        self.assertEqual(self.mod.window_state([20, 24, 0], 'low'), 'alarm')
        self.assertEqual(self.mod.window_state([20, 25, 0], 'low'), 'ok')
        self.assertEqual(self.mod.window_state([20, None, 0], 'low'), 'insufficient data')
        self.assertEqual(self.mod.window_state([20], 'high'), 'insufficient data')
        self.assertEqual(self.mod.window_state([True, 65], 'high'), 'insufficient data')


if __name__ == '__main__':
    unittest.main()
