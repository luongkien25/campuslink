"""Callback Heat: HTTP fixture that, chi gia lap boundary Docker/systemd."""
import contextlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime import Failure, atomic_json, boot_id, read_json


@contextlib.contextmanager
def server(code=200):
    class Handler(BaseHTTPRequestHandler):
        seen = []
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            self.seen.append((self.path, self.headers.get('X-Auth-Token'), json.loads(body)))
            self.send_response(code)
            self.end_headers()
        def log_message(self, *args):
            pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}/heat-api/v1/test/resources/ready/signal', Handler.seen
    finally:
        http.shutdown(); http.server_close(); thread.join()


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'signal_ready.py').is_file(), 'callback chua implement')
        self.mod = importlib.import_module('signal_ready')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.state = self.path / 'state'
        self.state.mkdir(mode=0o700)
        self.config = self.state / 'signal.json'
        self.attempt = dict(instance_id='f0506604-a133-460b-9aa1-99ce6aa01c36', boot_id=boot_id(),
                            started=time.monotonic()-1, deadline=time.monotonic()+20)
        atomic_json(self.state / 'heat-attempt.json', self.attempt)
        ready = dict(boot_id=boot_id(), started=time.monotonic(), deadline=time.monotonic()+15, generation='new')
        for name in ('secrets', 'guard', 'ready'):
            atomic_json(self.state / (name + '.json'), ready)

    def config_for(self, url):
        atomic_json(self.config, dict(endpoint=url, token='dummy-token-for-local-test'))

    def runtime(self, argv, **kwargs):
        if argv[0] == 'curl':
            # Signal HTTP that; assert token chi trong header file, khong argv.
            self.assertNotIn('dummy-token-for-local-test', ' '.join(argv))
            self.assertIn('--disable', argv)
            self.assertNotIn('--location', argv)
            return subprocess.run(argv, capture_output=True, **kwargs)
        if argv[0] == 'iptables':
            output = b''
            if '-S' in argv:
                output = (b'-A FORWARD -j DOCKER-USER\n' if argv[-1] == 'FORWARD'
                          else b'-A DOCKER-USER -d 169.254.169.254/32 -j DROP\n')
            return subprocess.CompletedProcess(argv, 0, output, b'')
        if argv[0] == 'docker':
            return subprocess.CompletedProcess(argv, 0, b'{"Status":"running","RestartCount":0,"NetworkMode":"bridge"}', b'')
        return subprocess.CompletedProcess(argv, 0, b'PONG\n', b'')

    def send(self, status='SUCCESS', run=None):
        # probe HTTP cuc bo duoc fake, callback POST van di qua curl that.
        with patch.object(self.mod, 'probe', return_value=True):
            return self.mod.send_status(self.config, self.state, status, run=run or self.runtime)

    def test_success_posts_native_payload_once_and_removes_token(self):
        with server() as (url, seen):
            self.config_for(url)
            self.send()
            self.send()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][1], 'dummy-token-for-local-test')
        self.assertEqual(seen[0][2]['status'], 'SUCCESS')
        self.assertFalse(self.config.exists())
        self.assertEqual(read_json(self.state / 'heat-sent.json')['status'], 'SUCCESS')
        self.assertNotIn('dummy-token', (self.state / 'heat-sent.json').read_text())

    def test_no_success_with_missing_stale_or_expired_ready(self):
        with server() as (url, seen):
            self.config_for(url)
            ready = read_json(self.state / 'ready.json')
            for bad in (dict(ready, boot_id='old'), dict(ready, generation='old'), dict(ready, deadline=0),
                        dict(ready, started=self.attempt['started']-1)):
                atomic_json(self.state / 'ready.json', bad)
                with self.assertRaises(Failure):
                    self.send()
            (self.state / 'ready.json').unlink()
            with self.assertRaises(Failure):
                self.send()
        self.assertEqual(seen, [])

    def test_live_probe_and_guard_required(self):
        with server() as (url, seen):
            self.config_for(url)
            with patch.object(self.mod, 'probe', return_value=False), self.assertRaises(Failure):
                self.mod.send_status(self.config, self.state, 'SUCCESS', run=self.runtime)
            (self.state / 'guard.json').unlink()
            with self.assertRaises(Failure):
                self.send()
        self.assertEqual(seen, [])

    def test_first_probe_failure_allows_failure_handler_to_notify_heat(self):
        with server() as (url, seen):
            self.config_for(url)
            with patch.object(self.mod,'probe',return_value=False), self.assertRaises(Failure):
                self.mod.send_status(self.config,self.state,'SUCCESS',run=self.runtime)
            self.send('FAILURE')
        self.assertEqual([row[2]['status'] for row in seen],['FAILURE'])

    def test_failure_does_not_require_ready_and_cannot_become_success(self):
        (self.state / 'ready.json').unlink()
        with server() as (url, seen):
            self.config_for(url)
            self.send('FAILURE')
            with self.assertRaises(Failure):
                self.send('SUCCESS')
        self.assertEqual([r[2]['status'] for r in seen], ['FAILURE'])

    def test_redirect_auth_and_timeout_fail_without_marker_or_token_left(self):
        for code in (302, 401, 403, 404, 500):
            with self.subTest(code=code), server(code) as (url, seen):
                self.config_for(url)
                with self.assertRaises(Failure):
                    self.send()
                self.assertFalse((self.state / 'heat-sent.json').exists())
                self.assertFalse(self.config.exists())
                self.assertLessEqual(len(seen), 3)

    def test_old_boot_and_expired_attempt_never_post(self):
        with server() as (url, seen):
            self.config_for(url)
            for bad in (dict(self.attempt, boot_id='old'), dict(self.attempt, deadline=0)):
                atomic_json(self.state / 'heat-attempt.json', bad)
                with self.assertRaises(Failure):
                    self.send()
        self.assertEqual(seen, [])

    def test_rejects_unsafe_config_and_endpoint(self):
        for url in ('http://example.org/heat-api/x', 'http://10.11.0.10/not-heat',
                    'http://user:pw@10.11.0.10/heat-api/x', 'http://10.11.0.10/heat-api/x?token=x'):
            self.config_for(url)
            with self.assertRaises(Failure):
                self.send()
        self.config_for('http://10.11.0.10/heat-api/x')
        self.config.chmod(0o644)
        with self.assertRaises(Failure):
            self.send()

    def test_transport_timeout_is_redacted_and_budget_not_reset(self):
        self.config_for('http://10.11.0.10/heat-api/x')
        observed = []
        def timeout(argv, **kwargs):
            if argv[0] != 'curl':
                return self.runtime(argv, **kwargs)
            observed.append(kwargs['timeout'])
            raise Failure('command-unavailable-or-timeout')
        with self.assertRaises(Failure):
            self.send(run=timeout)
        self.assertEqual(len(observed), 1)
        self.assertLessEqual(observed[0], 5)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.state / 'heat-sent.json').exists())

    def test_guard_order_failure_cannot_post_success(self):
        self.config_for('http://10.11.0.10/heat-api/x')
        def bad_guard(argv, **kwargs):
            if argv[0] == 'iptables' and '-S' in argv:
                return subprocess.CompletedProcess(argv, 0, b'-A FORWARD -j ACCEPT\n', b'')
            return self.runtime(argv, **kwargs)
        with self.assertRaises(Failure):
            self.send(run=bad_guard)
        self.assertFalse((self.state / 'heat-sent.json').exists())

    def test_success_retry_rechecks_ready_and_same_generation(self):
        for fault in ('missing-ready', 'new-generation', 'live-probe-failed'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temp:
                # Moi fault co attempt rieng, terminal marker khong duoc dung lai.
                import shutil
                state = Path(temp)/'state'
                shutil.copytree(self.state, state); state.chmod(0o700)
                config = state/'signal.json'
                atomic_json(config,dict(endpoint='http://10.11.0.10/heat-api/x',token='dummy-token'))
                posts = []
                def run(argv, **kwargs):
                    if argv[0] != 'curl':
                        return self.runtime(argv, **kwargs)
                    posts.append(argv)
                    if len(posts)==1:
                        if fault=='missing-ready':
                            (state/'ready.json').unlink()
                        if fault=='new-generation':
                            for name in ('secrets','guard','ready'):
                                value=read_json(state/(name+'.json'));value['generation']='changed'
                                atomic_json(state/(name+'.json'),value)
                        return subprocess.CompletedProcess(argv,0,b'503',b'')
                    return subprocess.CompletedProcess(argv,0,b'200',b'')
                with patch.object(self.mod,'probe',side_effect=[True,False] if fault=='live-probe-failed' else None,
                                  return_value=True), self.assertRaises(Failure):
                    self.mod.send_status(config,state,'SUCCESS',run=run)
                self.assertEqual(len(posts),1)
                self.assertFalse((state/'heat-sent.json').exists())
                self.assertFalse(config.exists())


class ActivationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'heat_bootstrap.py').is_file(), 'activation chua implement')
        self.mod = importlib.import_module('heat_bootstrap')

    def test_config_and_attempt_published_before_start_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); base.chmod(0o700)
            config = base / 'config'; config.mkdir(mode=0o700)
            state = base / 'state'
            atomic_json(config / 'bootstrap.pending.json', {'credential_id': 'dummy'})
            atomic_json(config / 'heat.pending.json', {'endpoint': 'http://10.11.0.10/heat-api/x', 'token': 'dummy'})
            observed = []
            def run(argv, **kwargs):
                observed.append(argv)
                if argv[1:3] == ['start', 'campuslink-heat-signal.service']:
                    self.assertTrue((config / 'bootstrap.json').exists())
                    self.assertTrue((state / 'signal.json').exists())
                    attempt = read_json(state / 'heat-attempt.json')
                    self.assertLessEqual(attempt['deadline'] - attempt['started'], 180)
                return subprocess.CompletedProcess(argv, 0, b'', b'')
            self.mod.activate(config, state, instance_id='f0506604-a133-460b-9aa1-99ce6aa01c36', run=run)
            self.assertFalse((config / 'heat.pending.json').exists())
            self.assertEqual(observed[-1][1:3], ['start', 'campuslink-heat-signal.service'])
            with self.assertRaises(Failure):
                self.mod.activate(config, state, instance_id='f0506604-a133-460b-9aa1-99ce6aa01c36', run=run)

    def test_bootstrap_failure_reports_failure_and_does_not_run_app_manually(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); base.chmod(0o700)
            atomic_json(base / 'bootstrap.pending.json', {'credential_id': 'dummy'})
            atomic_json(base / 'heat.pending.json', {'endpoint': 'http://10.11.0.10/heat-api/x', 'token': 'dummy'})
            calls = []
            def run(argv, **kwargs):
                calls.append(argv)
                return subprocess.CompletedProcess(argv, int(argv[1:3] == ['start', 'campuslink-heat-signal.service']), b'', b'')
            with self.assertRaises(Failure):
                self.mod.activate(base, base / 'state', instance_id='f0506604-a133-460b-9aa1-99ce6aa01c36', run=run)
            self.assertEqual(calls[-1][1:3], ['start', 'campuslink-heat-failure.service'])


if __name__ == '__main__':
    unittest.main()
