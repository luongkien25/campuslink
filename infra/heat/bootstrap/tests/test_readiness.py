from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT / 'readiness.py').exists(), 'readiness chua implement')
        import readiness
        from runtime import Deadline
        import time
        self.mod = readiness
        self.deadline = Deadline(time.monotonic() + 10)
        self.health = b'{"status":"pass"}'
        self.code = b'200'
        self.redis = b'PONG\n'
        self.container = b'{"Status":"running","RestartCount":0,"NetworkMode":"bridge"}'
        self.inspect_code = 0

    def run_command(self, argv, **kwargs):
        if argv[0] == 'curl':
            return subprocess.CompletedProcess(argv, 0, self.health + b'\n' + self.code, b'')
        if argv[0] == 'docker':
            return subprocess.CompletedProcess(argv, self.inspect_code, self.container, b'')
        return subprocess.CompletedProcess(argv, 0, self.redis, b'')

    def test_ready_requires_http_pass_and_exact_pong(self):
        self.assertTrue(self.mod.probe(self.deadline, run=self.run_command))
        for health, code, redis in [(b'{"status":"fail"}', b'200', b'PONG'),
                                    (b'not-json', b'200', b'PONG'),
                                    (b'{"status":"pass"}', b'503', b'PONG'),
                                    (b'{"status":"pass"}', b'200', b'NOAUTH')]:
            self.health, self.code, self.redis = health, code, redis
            self.assertFalse(self.mod.probe(self.deadline, run=self.run_command))

    def test_container_exit_restart_or_host_network_fail_fast(self):
        for info in [dict(Status='exited', RestartCount=0, NetworkMode='bridge'),
                     dict(Status='running', RestartCount=1, NetworkMode='bridge'),
                     dict(Status='running', RestartCount=0, NetworkMode='host')]:
            import json
            self.container = json.dumps(info).encode()
            with self.assertRaises(self.mod.Failure):
                self.mod.probe(self.deadline, run=self.run_command)

    def test_expired_shared_budget(self):
        from runtime import Deadline
        with self.assertRaises(self.mod.Failure):
            self.mod.probe(Deadline(0), run=self.run_command)

    def test_waits_for_container_creation_after_exec_unit_start(self):
        self.inspect_code = 1
        self.assertFalse(self.mod.probe(self.deadline, run=self.run_command))
        self.inspect_code = 0
        self.container = b'{"Status":"created","RestartCount":0,"NetworkMode":"bridge"}'
        self.assertFalse(self.mod.probe(self.deadline, run=self.run_command))
        self.container = b'{"Status":"running","RestartCount":0,"NetworkMode":"bridge"}'
        self.assertTrue(self.mod.probe(self.deadline, run=self.run_command))


if __name__ == '__main__':
    unittest.main()
