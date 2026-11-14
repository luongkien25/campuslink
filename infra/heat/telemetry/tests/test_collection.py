"""API doubles chi tai ranh gioi SDK; whitelist/test loi khong can cloud."""
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from test_cpu import A, B, PROJECT, NOW

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))


class Manager:
    def __init__(self, query):
        self.query = query

    def search(self, resource_type, query):
        if resource_type != 'instance' or query != self.query:
            raise AssertionError('wrong API query')
        return [dict(id=ident, project_id=PROJECT, vcpus=1, server_group='campuslink-app',
                     ended_at=None, metrics={'cpu': ident}, access_token='FAKE_SECRET_ONLY') for ident in (A, B)]


class Metrics:
    def get(self, metric_id):
        return dict(id=metric_id, unit='ns', created_by_user_id='DO_NOT_EXPORT', archive_policy={
            'name': 'ceilometer-high-rate', 'aggregation_methods': ['mean', 'rate:mean'],
            'definition': [{'granularity': 60, 'points': 60, 'timespan': 3600}],
            'password': 'FAKE_SECRET_ONLY'})

    def get_measures(self, metric_id, *, aggregation, granularity, start, stop):
        if metric_id not in (A, B) or granularity != 60 or not start or not stop:
            raise AssertionError('unbounded or wrong metric request')
        return [((NOW-timedelta(minutes=m)).isoformat(), 60.0, 1e12+m)
                for m in range(8, 1, -1)]


class CollectionTests(unittest.TestCase):
    def setUp(self):
        path = BASE/'collect_metrics.py'
        self.assertTrue(path.exists(), 'collector chua implement')
        spec = importlib.util.spec_from_file_location('collect_metrics', path)
        self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
        self.query = {'and': [{'=': {'server_group': 'campuslink-app'}},
                              {'=': {'project_id': PROJECT}}, {'=': {'ended_at': None}}]}
        self.api = type('Api', (), {})()
        self.api.resource = Manager(self.query); self.api.metric = Metrics()

    def collect(self):
        return self.mod.collect(self.api, PROJECT, start=NOW-timedelta(minutes=10), stop=NOW, now=NOW)

    def test_whitelist_snapshot_uses_exact_project_group_active_query_and_bounded_reads(self):
        result = self.collect()
        self.assertEqual(result['query'], self.query)
        self.assertEqual([r['uuid'] for r in result['resources']], [A, B])
        text = json.dumps(result)
        for bad in ('FAKE_SECRET_ONLY', 'access_token', 'password', 'created_by_user_id'):
            self.assertNotIn(bad, text)
        self.assertEqual(result['resources'][0]['unit'], 'ns')
        self.assertEqual(len(result['resources'][0]['rows']), 14)

    def test_api_errors_never_echo_exception_or_fall_back_to_other_credentials(self):
        def fail(*args, **kwargs):
            raise RuntimeError('403 FAKE_SECRET_ONLY http://secret.example/?signature=secret')
        self.api.metric.get = fail
        with self.assertRaises(self.mod.CollectionError) as caught:
            self.collect()
        self.assertEqual(str(caught.exception), 'metric-collection-failed')

    def test_rejects_wrong_project_ended_missing_cpu_and_secret_in_allowed_fields(self):
        original = self.api.resource.search
        for field, value in [('project_id', 'b'*32), ('ended_at', NOW.isoformat()),
                             ('metrics', {}), ('id', 'FAKE_SECRET_ONLY')]:
            def changed(*args, **kwargs):
                rows = original(*args, **kwargs); rows[0][field] = value; return rows
            self.api.resource.search = changed
            with self.subTest(field=field), self.assertRaises(self.mod.CollectionError):
                self.collect()
        self.api.resource.search = original
        get = self.api.metric.get
        def bad_unit(*args):
            result = get(*args); result['unit'] = 'http://token.example'; return result
        self.api.metric.get = bad_unit
        with self.assertRaises(self.mod.CollectionError):
            self.collect()

    def test_rejects_unbounded_window_and_duplicate_ids(self):
        with self.assertRaises(self.mod.CollectionError):
            self.mod.collect(self.api, PROJECT, start=NOW-timedelta(days=1), stop=NOW, now=NOW)
        original = self.api.resource.search
        self.api.resource.search = lambda *a, **k: original(*a, **k)*2
        with self.assertRaises(self.mod.CollectionError):
            self.collect()


if __name__ == '__main__':
    unittest.main()
