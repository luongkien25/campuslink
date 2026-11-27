"""Offline regressions for shared demo wrappers. No SSH or cloud commands are run."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
HOST = ROOT / "ops/demo/demo-host-a.sh"
FORMAT = ROOT / "ops/demo/demo-json.py"
BASH = shutil.which("bash")
if Path("C:/Program Files/Git/bin/bash.exe").exists():
    BASH = "C:/Program Files/Git/bin/bash.exe"


class FormatTests(unittest.TestCase):
    def run_format(self, action, data, *args):
        import sys
        return subprocess.run([sys.executable, str(FORMAT), action, *args],
                              input=json.dumps(data), text=True, capture_output=True)

    def test_lb_input_is_read_and_real_member_returned(self):
        data = {"loadbalancer": {"listeners": [{"pools": [{"members": [
            {"address": "10.20.0.195", "operating_status": "ONLINE"}]}]}]}}
        result = self.run_format("member", data, "10.20.0.195")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "ONLINE")

    def test_unknown_alarm_does_not_authorize_failover(self):
        for data in ({}, {"enabled": False}, {"enabled": "unknown", "alarm_actions": []},
                     {"enabled": True, "alarm_actions": []},
                     {"enabled": False, "alarm_actions": ["private-url"]}):
            with self.subTest(data=data):
                self.assertNotEqual(self.run_format("alarm-disabled", data).returncode, 0)
        self.assertEqual(self.run_format("alarm-disabled", {"enabled": False, "alarm_actions": []}).returncode, 0)

    def test_history_and_alarm_summary_do_not_print_action_urls(self):
        secret = "https://private.example/token-value"
        result = self.run_format("alarm", {"enabled": True, "state": "ok", "alarm_actions": [secret]}, "high")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(secret, result.stdout + result.stderr)
        result = self.run_format("history", [{"type": "state transition", "timestamp": "2026-11-27T12:00:00Z",
                                  "detail": json.dumps({"state": "alarm", "reason": secret})}], "5")
        self.assertEqual(result.returncode, 0)
        self.assertIn("state=alarm", result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)


@unittest.skipUnless(BASH, "Bash required")
class WrapperTests(unittest.TestCase):
    def run_shell(self, commands):
        script = "source " + shlex.quote(HOST.as_posix()) + "\n" + commands
        return subprocess.run([BASH, "-c", script], text=True, capture_output=True)

    def test_own_member_identity_does_not_call_sudo(self):
        result = self.run_shell('ACTOR=tv2\nsudo() { echo WRONG_SUDO; return 99; }\nas_user tv2 printf own-identity')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "own-identity")

    def test_member_cannot_borrow_another_identity(self):
        result = self.run_shell('ACTOR=tv3\nsudo() { echo WRONG_SUDO; return 99; }\nas_user tv2 printf other')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("WRONG_SUDO", result.stdout)

    def test_tv3_cannot_trigger_failover(self):
        result = self.run_shell('ACTOR=tv3\ncmd_fail_stop() { echo WRONG_MUTATION; }\nmain fail-stop')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("WRONG_MUTATION", result.stdout)

    def test_unknown_alarm_prevents_any_stop_request(self):
        result = self.run_shell('ACTOR=tv2\nalarms_disabled() { return 1; }\nos_tv2() { echo WRONG_MUTATION; }\nmain fail-stop')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("WRONG_MUTATION", result.stdout)

    def test_full_sha256_checks_suffix_not_just_first_16_chars(self):
        digest = hashlib.sha256(b"test-payload").hexdigest()
        invalid = digest[:-1] + ("0" if digest[-1] != "0" else "1")
        script = r'''
ACTOR=tv3
as_user() { shift; "$@"; }
http_code() { echo 401; }
os_tv3() {
  case "$1 $2" in
    'volume list') echo volume-in-use ;;
    'object list') echo db/shlink-demo.dump ;;
    'object save')
      case "$6" in
        *.sha256) printf '%s  dump\n' REPLACE_DIGEST > "$4" ;;
        *) printf test-payload > "$4" ;;
      esac ;;
    *) return 1 ;;
  esac
}
cmd_hm34
'''
        good = self.run_shell(script.replace("REPLACE_DIGEST", shlex.quote(digest)))
        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        bad = self.run_shell(script.replace("REPLACE_DIGEST", shlex.quote(invalid)))
        self.assertNotEqual(bad.returncode, 0, bad.stdout + bad.stderr)
        self.assertNotIn("PASS: full", bad.stdout)


if __name__ == "__main__":
    unittest.main()
