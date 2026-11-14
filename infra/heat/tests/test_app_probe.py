"""Traffic core: fresh TCP/Request ID, khong dung backend gia trong app."""
import contextlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HEAT = Path(__file__).resolve().parents[1]


def module(name):
    path = HEAT / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def serving(status=401, request_id=True):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        ports = []; count = 0
        def do_GET(self):
            self.ports.append(self.client_address[1]); type(self).count += 1
            self.send_response(status)
            if request_id:
                self.send_header('X-Request-ID', 'req-' + str(self.count))
            self.send_header('Location', 'https://example.org/target')
            self.send_header('Content-Length', '0'); self.end_headers()
        def log_message(self, *args):
            pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}', Handler
    finally:
        http.shutdown(); http.server_close(); thread.join()


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HEAT / 'probe_app_pool.py').exists(), 'probe chua implement')
        self.mod = module('probe_app_pool')

    def test_fresh_tcp_expected_401_ids_no_body(self):
        with serving() as (url, handler):
            report = self.mod.sample(url, count=6, host='s.example.test')
        self.assertTrue(report['passed'])
        self.assertEqual(len(set(handler.ports)), 6)
        self.assertEqual([r['request_id'] for r in report['requests']], ['req-'+str(i) for i in range(1,7)])
        self.assertNotIn('body', json.dumps(report))

    def test_redirect_and_missing_request_id_fail_auth_probe_without_follow(self):
        for status, has_id in ((302, True), (200, True), (401, False)):
            with serving(status, has_id) as (url, handler):
                report = self.mod.sample(url, count=2, host='s.example.test')
                self.assertFalse(report['passed']); self.assertEqual(handler.count, 2)

    def test_redirect_smoke_checks_location_without_follow(self):
        with serving(302) as (url, handler):
            report = self.mod.sample(url, count=2, host='s.example.test',
                                     path='/test-link', redirect_target='https://example.org/target')
            self.assertTrue(report['passed']); self.assertEqual(handler.count, 2)

    def test_mapping_requires_each_request_exactly_one_guest_and_all_expected_guests(self):
        ids = ['req-1', 'req-2', 'req-3']
        logs = {'vm-a': ['req-1','req-3'], 'vm-b': ['req-2']}
        good = self.mod.correlate(ids, logs, {'vm-a','vm-b'})
        self.assertTrue(good['passed']); self.assertEqual(good['counts'], {'vm-a':2,'vm-b':1})
        self.assertFalse(self.mod.correlate(ids, {'vm-a':ids,'vm-b':[]}, {'vm-a','vm-b'})['passed'])
        self.assertFalse(self.mod.correlate(ids, dict(logs, **{'vm-c':['req-1']}), {'vm-a','vm-b'})['passed'])
        self.assertFalse(self.mod.correlate(ids, {'vm-a':['req-1'],'vm-b':['req-2']}, {'vm-a','vm-b'})['passed'])

    def test_url_host_count_reject_invalid_inputs(self):
        for url, host, count in [('http://user:pw@127.0.0.1','s.example.test',1),
                                 ('http://127.0.0.1?token=x','s.example.test',1),
                                 ('http://127.0.0.1','bad\r\nHost:x',1),
                                 ('http://127.0.0.1','s.example.test',0)]:
            with self.assertRaises(ValueError):
                self.mod.sample(url, count=count, host=host)

    def test_cli_correlates_saved_report_without_new_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp)
            report=temp/'report.json'; logs=temp/'guests.json'
            saved={'passed':True,'mode':'auth-deny','requests':[
                {'request_id':'req-1','status':401,'passed':True},
                {'request_id':'req-2','status':401,'passed':True}]}
            report.write_text(json.dumps(saved));logs.write_text(json.dumps({'vm-a':['req-1'],'vm-b':['req-2']}))
            argv=[sys.executable,'-B',str(HEAT/'probe_app_pool.py'),'--report',str(report),
                  '--guest-request-ids',str(logs),'--expect-guest','vm-a','--expect-guest','vm-b']
            result=subprocess.run(argv,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            parsed=json.loads(result.stdout)
            self.assertEqual(parsed['requests'],saved['requests'])
            self.assertEqual(parsed['backends']['counts'],{'vm-a':1,'vm-b':1})


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HEAT / 'collect_app_timeline.py').exists(), 'timeline chua implement')
        self.mod = module('collect_app_timeline')

    def test_timeline_utc_and_per_unit_order_requires_all_milestones(self):
        kinds = ['vm_active','local_ready','signal_ack','wait_complete','member_active','first_request']
        events = [dict(instance_id='vm-a',event=k,utc=f'2026-11-13T12:00:0{i}Z') for i,k in enumerate(kinds)]
        report = self.mod.summarize(events)
        self.assertTrue(report['passed'])
        self.assertEqual(report['instances']['vm-a']['active_to_request_seconds'], 5)
        self.assertFalse(self.mod.summarize(events[:-1])['passed'])
        events[0]['utc'] = '2026-11-13T12:00:00'
        with self.assertRaises(ValueError):
            self.mod.summarize(events)

    def test_timeline_does_not_approve_member_before_readiness(self):
        events = [dict(instance_id='vm-a',event=k,utc=f'2026-11-13T12:00:0{i}Z') for i,k in
                  enumerate(['vm_active','member_active','local_ready','signal_ack','wait_complete','first_request'])]
        self.assertFalse(self.mod.summarize(events)['passed'])

    def test_engine_can_complete_wait_before_client_receives_http_ack(self):
        # Native Heat event co do phan giai giay; HTTP ACK la quan sat phia client.
        events=[{'instance_id':'vm-a','event':kind,'utc':stamp} for kind,stamp in [
            ('vm_active','2026-11-13T13:36:56Z'),
            ('local_ready','2026-11-13T13:37:24.200042Z'),
            ('signal_ack','2026-11-13T13:37:25.129216Z'),
            ('wait_complete','2026-11-13T13:37:25Z'),
            ('member_active','2026-11-13T13:37:27Z'),
            ('first_request','2026-11-13T13:40:16.843114Z')]]
        self.assertTrue(self.mod.summarize(events)['passed'])


if __name__ == '__main__':
    unittest.main()
