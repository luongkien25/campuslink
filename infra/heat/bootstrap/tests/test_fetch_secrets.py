import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'fetch_secrets.py').exists(), 'bootstrap chua duoc implement')
        import fetch_secrets
        self.mod = fetch_secrets
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.calls = []
        self.overrides = {}
        self.delay = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                outer.calls.append(('POST', self.path, body, self.headers.get('X-Auth-Token')))
                self.reply(201, b'{"token": {}}', {'X-Subject-Token': 'fake-token-only'})

            def do_GET(self):
                outer.calls.append(('GET', self.path, b'', self.headers.get('X-Auth-Token')))
                data = b'a' * 48 if self.path.endswith('db_password') else b'tcp://default:' + b'b' * 48 + b'@10.20.0.10:6379\n'
                self.reply(200, data, {})

            def reply(self, code, body, headers):
                time.sleep(outer.delay)
                code, body, headers = outer.overrides.get(self.path, (code, body, headers))
                self.send_response(code)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except BrokenPipeError:
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.config = dict(keystone_url=self.base + '/identity/v3/auth/tokens',
                           swift_account_url=self.base + '/v1/AUTH_test',
                           credential_id='c' * 32, credential_secret='fake-credential-only')

    def tearDown(self):
        if hasattr(self, 'server'):
            self.server.shutdown()
            self.server.server_close()
        if hasattr(self, 'tmp'):
            self.tmp.cleanup()

    def fetch(self, **kwargs):
        return self.mod.fetch(self.config, self.root / 'secrets', self.root / 'state', **kwargs)

    def test_token_201_and_exact_gets_publish_permissions(self):
        import subprocess
        run = subprocess.run
        argv = []
        def record(args, **kwargs):
            argv.append(args)
            return run(args, **kwargs)
        with patch('subprocess.run', side_effect=record), patch.dict(os.environ, {'http_proxy': 'http://127.0.0.1:1', 'HTTP_PROXY': 'http://127.0.0.1:1'}):
            state = self.fetch()
        self.assertEqual([(x[0], x[1]) for x in self.calls], [
            ('POST', '/identity/v3/auth/tokens'),
            ('GET', '/v1/AUTH_test/campus-secrets/app/db_password'),
            ('GET', '/v1/AUTH_test/campus-secrets/app/redis_servers')])
        self.assertEqual(self.calls[1][3], 'fake-token-only')
        auth = json.loads(self.calls[0][2])['auth']['identity']
        self.assertEqual(auth['methods'], ['application_credential'])
        self.assertEqual(auth['application_credential']['secret'], 'fake-credential-only')
        self.assertEqual(stat.S_IMODE((self.root / 'secrets').stat().st_mode), 0o700)
        for name in ('db_password', 'redis_servers'):
            self.assertEqual(stat.S_IMODE((self.root / 'secrets' / name).stat().st_mode), 0o444)
        self.assertLessEqual(state['deadline'] - state['started'], 180)
        self.assertNotIn('fake-', json.dumps(state))
        self.assertNotIn('fake-', repr(argv))
        for call in argv:
            self.assertTrue(Path(call[call.index('--output') + 1]).is_relative_to(self.root / 'state'))

    def test_failures_never_publish_or_leave_stale_set(self):
        failures = [(401, b'private-error', {}), (403, b'', {}), (404, b'', {}),
                    (200, b'', {}), (200, b'x' * 5000, {}), (200, b'bad-uri', {}),
                    (302, b'', {'Location': self.base + '/leaked'})]
        path = '/v1/AUTH_test/campus-secrets/app/redis_servers'
        for failure in failures:
            with self.subTest(failure=failure[0:1]):
                self.overrides.clear()
                self.fetch()
                self.overrides[path] = failure
                with self.assertRaises(self.mod.Failure) as caught:
                    self.fetch()
                self.assertNotIn('private-error', str(caught.exception))
                self.assertFalse((self.root / 'secrets').exists())
                self.assertFalse((self.root / 'state' / 'secrets.json').exists())
        self.assertNotIn('/leaked', [c[1] for c in self.calls])

    def test_bad_token_response_and_redirect_fail_closed(self):
        for response in [(201, b'{}', {}), (201, b'not-json', {'X-Subject-Token': 'fake-token-only'}),
                         (302, b'', {'Location': self.base + '/leaked'})]:
            self.overrides['/identity/v3/auth/tokens'] = response
            before = len(self.calls)
            with self.assertRaises(self.mod.Failure):
                self.fetch()
            self.assertEqual(len(self.calls) - before, 1)
            self.assertFalse((self.root / 'secrets').exists())

    def test_curl_config_cannot_enable_redirect(self):
        (self.root / '.curlrc').write_text('location\n')
        self.overrides['/identity/v3/auth/tokens'] = (302, b'', {'Location': self.base + '/leaked'})
        with patch.dict(os.environ, {'CURL_HOME': str(self.root)}):
            with self.assertRaises(self.mod.Failure):
                self.fetch()
        self.assertNotIn('/leaked', [c[1] for c in self.calls])

    def test_retry_limit_and_shared_deadline(self):
        self.overrides['/identity/v3/auth/tokens'] = (503, b'', {})
        with self.assertRaises(self.mod.Failure):
            self.fetch()
        self.assertEqual(len(self.calls), 3)
        self.calls.clear()
        self.overrides.clear()
        started = time.monotonic()
        with self.assertRaises(self.mod.Failure):
            self.fetch(budget=0)
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(self.calls, [])

    def test_slow_responses_share_one_deadline_without_partial_publish(self):
        self.delay = 0.08
        started = time.monotonic()
        with self.assertRaises(self.mod.Failure):
            self.fetch(budget=0.2)
        self.assertLess(time.monotonic() - started, 1)
        self.assertFalse((self.root / 'secrets').exists())
        self.assertFalse((self.root / 'state' / 'secrets.json').exists())

    def test_invalid_database_password_rejected(self):
        self.overrides['/v1/AUTH_test/campus-secrets/app/db_password'] = (200, b'not-a-hex-password', {})
        with self.assertRaises(self.mod.Failure):
            self.fetch()
        self.assertFalse((self.root / 'secrets').exists())

    def test_cli_does_not_print_exception_or_secret(self):
        import contextlib
        import io
        import runtime
        output = io.StringIO()
        def fail():
            raise ValueError('fake-sensitive-response')
        with patch.object(runtime, 'require_guest'), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit):
                runtime.cli(fail)
        self.assertEqual(output.getvalue(), 'FAIL: runtime precondition or operation failed\n')

    def test_refetch_after_run_reset_and_reject_symlink(self):
        first = self.fetch()
        second = self.fetch()
        self.assertNotEqual(first['generation'], second['generation'])
        self.assertEqual(len(self.calls), 6)
        other = self.root / 'untouched'
        other.write_text('keep')
        (self.root / 'secrets' / 'db_password').unlink()
        (self.root / 'secrets' / 'db_password').symlink_to(other)
        with self.assertRaises(self.mod.Failure):
            self.fetch()
        self.assertEqual(other.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
