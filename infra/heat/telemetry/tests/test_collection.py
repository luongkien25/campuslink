"""API doubles chi tai ranh gioi SDK; whitelist/test loi khong can cloud."""
from datetime import timedelta
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from test_cpu import A, B, PROJECT, NOW

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
VCPU = '44444444-4444-4444-8444-444444444444'


class Manager:
    def __init__(self, query):
        self.query = query

    def search(self, resource_type, query):
        if resource_type != 'instance' or query != self.query:
            raise AssertionError('wrong API query')
        return [dict(id=ident, project_id=PROJECT, server_group='campuslink-app',
                     ended_at=None, deleted_at=None, metrics={'cpu': ident, 'vcpus': VCPU},
                     access_token='FAKE_SECRET_ONLY') for ident in (A, B)]


class Metrics:
    def get(self, metric_id):
        return dict(id=metric_id, unit='vcpu' if metric_id == VCPU else 'ns', created_by_user_id='DO_NOT_EXPORT', archive_policy={
            'name': 'ceilometer-high-rate', 'aggregation_methods': ['mean', 'rate:mean'],
            'definition': [{'granularity': 60, 'points': 60, 'timespan': 3600}],
            'password': 'FAKE_SECRET_ONLY'})

    def get_measures(self, metric_id, *, aggregation, granularity, start, stop):
        if metric_id not in (A, B, VCPU) or granularity != 60 or not start or not stop:
            raise AssertionError('unbounded or wrong metric request')
        return [((NOW-timedelta(minutes=m)).isoformat(), 60.0,
                 1.0 if metric_id == VCPU else (1e12+(8-m)*36e9 if aggregation == 'mean' else 36e9))
                for m in range(8, 1, -1)]


class CollectionTests(unittest.TestCase):
    def setUp(self):
        path = BASE/'collect_metrics.py'
        self.assertTrue(path.exists(), 'collector chua implement')
        spec = importlib.util.spec_from_file_location('collect_metrics', path)
        self.mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.mod)
        self.query = {'and': [{'=': {'server_group': 'campuslink-app'}},
                              {'=': {'project_id': PROJECT}}, {'=': {'ended_at': None}},
                              {'=': {'deleted_at': None}}]}
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
        self.assertEqual(result['resources'][0]['vcpus'], 1)
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
        for field, value in [('project_id', 'b'*32), ('ended_at', NOW.isoformat()), ('deleted_at', NOW.isoformat()),
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

    def test_live_client_duration_strings_vcpu_metric_and_analyzer_integration(self):
        get = self.api.metric.get
        def live_metric(*args):
            result = get(*args)
            result['archive_policy']['definition'] = [
                {'granularity': '0:00:01', 'points': 3600, 'timespan': '1:00:00'},
                {'granularity': '0:01:00', 'points': 1440, 'timespan': '1 day, 0:00:00'}]
            return result
        self.api.metric.get = live_metric
        snapshot = self.collect()
        self.assertEqual(snapshot['resources'][0]['archive_policy']['definition'][1]['granularity'], 60)
        import analyze_cpu
        report = analyze_cpu.analyze(snapshot, (A, B), now=NOW,
                                    max_age_seconds=120, rate_semantics='delta-ns')
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['group_cpu_percent'], [60.0]*6)

    def test_missing_or_changing_vcpus_cannot_be_guessed_from_flavor_name(self):
        original = self.api.metric.get_measures
        for mode in ('missing', 'changing'):
            def measured(metric_id, **kwargs):
                rows = original(metric_id, **kwargs)
                if metric_id == VCPU:
                    if mode == 'missing': return []
                    rows[-1] = (rows[-1][0], 60, 2.0)
                return rows
            self.api.metric.get_measures = measured
            with self.subTest(mode=mode), self.assertRaises(self.mod.CollectionError):
                self.collect()

    def test_requested_start_is_aligned_to_60_second_bucket_before_api_read(self):
        original = self.api.metric.get_measures
        def measured(metric_id, **kwargs):
            if kwargs['start'] != '2026-11-14T11:58:00+00:00':
                raise ValueError('API rounds start down to bucket; request explicit boundary')
            return original(metric_id, **kwargs)
        self.api.metric.get_measures = measured
        result = self.mod.collect(self.api, PROJECT, start=NOW-timedelta(minutes=10)+timedelta(seconds=17),
                                  stop=NOW, now=NOW)
        self.assertEqual(len(result['resources']), 2)

    def cli(self, *, cloud_name='campus-tv2', project_id=PROJECT, auth_error=False):
        api = self.api
        class Session:
            timeout = None
            def get_project_id(self):
                if auth_error:
                    raise TimeoutError('FAKE_SECRET_ONLY http://auth/?token=secret')
                return project_id
        session = Session()
        region = types.SimpleNamespace(config={'interface': 'public'}, region_name='RegionOne',
                                       get_session=lambda: session)
        class Config:
            def __init__(self, *, load_envvars):
                if load_envvars:
                    raise AssertionError('environment auth overrides must be disabled')
            def get_one(self, *, cloud):
                if cloud != 'campus-tv2':
                    raise AssertionError('unexpected cloud')
                return region
        # Chu ky Client that tren A: chi nhan adapter_options/session_options.
        def client(session=None, adapter_options=None, session_options=None):
            if session.timeout != 10 or adapter_options != {'interface': 'public', 'region_name': 'RegionOne'}:
                raise AssertionError('SDK adapter/timeout contract')
            return api
        modules = {name: types.ModuleType(name) for name in (
            'openstack', 'openstack.config', 'gnocchiclient', 'gnocchiclient.v1', 'gnocchiclient.v1.client')}
        modules['openstack.config'].OpenStackConfig = Config
        modules['gnocchiclient.v1.client'].Client = client
        argv = ['collect_metrics.py', '--project', PROJECT,
                '--start', (NOW-timedelta(minutes=10)).isoformat(), '--stop', NOW.isoformat()]
        output = io.StringIO()
        with patch.dict(sys.modules, modules), patch.dict('os.environ', {'OS_CLOUD': cloud_name}), \
                patch.object(sys, 'argv', argv), \
                patch.object(self.mod, 'datetime', types.SimpleNamespace(now=lambda zone: NOW)), \
                contextlib.redirect_stdout(output):
            rc = self.mod.main()
        return rc, output.getvalue()

    def test_cli_uses_real_client_constructor_contract_and_safe_snapshot(self):
        rc, output = self.cli()
        self.assertEqual(rc, 0, output)
        self.assertEqual(json.loads(output)['project_id'], PROJECT)
        self.assertNotIn('FAKE_SECRET_ONLY', output)

    def test_cli_wrong_cloud_project_and_auth_timeout_publish_no_snapshot_or_secret(self):
        for params in ({'cloud_name': 'admin'}, {'project_id': 'b'*32}, {'auth_error': True}):
            with self.subTest(params=params):
                rc, output = self.cli(**params)
                self.assertEqual(rc, 1)
                self.assertEqual(output, 'FAIL: metric collection unavailable; verify member API/schema/client on A, no payload printed\n')


if __name__ == '__main__':
    unittest.main()
