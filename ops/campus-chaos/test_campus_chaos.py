#!/usr/bin/env python3
# Kiem thu campus_chaos.py bang cloud, dong ho va bo lay mau gia (khong can cum OpenStack).
# Chay: python3 -m unittest ops/campus-chaos/test_campus_chaos.py   (tu thu muc goc repo)
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import campus_chaos as cc  # noqa: E402


class FakeClock:
    def __init__(self, t0=1000.0):
        self.t = t0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeCloud:
    def __init__(self, clock, role='app', fault_rc=0, revert_rc=0, members=None):
        self.clock, self.role = clock, role
        self.fault_rc, self.revert_rc = fault_rc, revert_rc
        self.calls = []
        self.fault_t = None
        self.revert_t = None
        self._members = members if members is not None else [
            {'id': 'm-1', 'name': 'm1', 'address': '10.20.0.185', 'status': 'ONLINE'},
            {'id': 'm-2', 'name': 'm2', 'address': '10.20.0.179', 'status': 'ONLINE'}]
        self.uploaded = []

    def server(self, name):
        return {'id': 'srv-1', 'name': name, 'status': 'ACTIVE', 'props': {'campus_role': self.role}, 'ip': '10.20.0.185'}

    def members(self, pool):
        return list(self._members)

    def port_of(self, server_id):
        return 'port-1'

    def apply(self, action, ctx, revert=False):
        self.calls.append((action, revert))
        if revert:
            self.revert_t = self.clock.now()
            return self.revert_rc, 'x'
        self.fault_t = self.clock.now()
        return self.fault_rc, 'x'

    def upload(self, container, path, name):
        self.uploaded.append((container, name))
        return True, ''


class FakeSampler:
    """Tao mau luu luong/trang thai theo thoi gian gia; hanh vi phu thuoc thoi diem gay loi va hoan tac."""

    def __init__(self, clock, cloud, errors_after_fault=False, boom=False):
        self.clock, self.cloud = clock, cloud
        self.errors_after_fault, self.boom = errors_after_fault, boom
        self.start_t = None

    def start(self):
        self.start_t = self.clock.now()

    def stop(self):
        pass

    def _faulty(self, t):
        f, r = self.cloud.fault_t, self.cloud.revert_t
        return f is not None and t >= f + 1 and (r is None or t < r + 2)

    def probes(self):
        if self.boom and self.cloud.fault_t is not None:
            raise RuntimeError('loi gia lap trong vong lap')
        out, t = [], self.start_t
        while t <= self.clock.now():
            k = int(round((t - self.start_t) / 0.25))
            if self._faulty(t):
                if self.errors_after_fault and k % 2 == 0:
                    out.append((t, 0, ''))
                else:
                    out.append((t, 200, 'chaos-lab-2'))
            else:
                out.append((t, 200, 'chaos-lab-1' if k % 2 else 'chaos-lab-2'))
            t += 0.25
        return out

    def statuses(self):
        out, t = [], self.start_t
        f, r = self.cloud.fault_t, self.cloud.revert_t
        while t <= self.clock.now():
            down = f is not None and t >= f + 2.5 and (r is None or t < r + 5)
            out.append((t, 'ERROR' if down else 'ONLINE', 1 if down else 2))
            t += 0.5
        return out


def scenario(**kw):
    sc = {'name': 'tat-vm-1', 'action': 'vm-stop', 'duration_s': 45, 'baseline_s': 10,
          'target': {'server': 'chaos-lab-1', 'pool': 'pool-1'},
          'probe': {'url': 'http://127.0.0.1:8080/', 'marker': 'chaos-lab-1'},
          'hypothesis': {'detect_within_s': 15, 'max_errors_after_detect': 0, 'recover_within_s': 60}}
    sc.update(kw)
    return sc


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, 'state', 'state.json')
        self.reports = os.path.join(self.tmp.name, 'reports')
        self.clock = FakeClock()

    def run_exp(self, sc, cloud, **skw):
        sampler = FakeSampler(self.clock, cloud, **skw)
        return cc.run_experiment(sc, cloud, lambda ctx, p: sampler, self.state, self.reports,
                                 clock=self.clock.now, sleep=self.clock.sleep)

    def test_happy_path(self):
        cloud = FakeCloud(self.clock)
        rep = self.run_exp(scenario(), cloud)
        self.assertEqual(rep['verdict'], 'PASS', rep['checks'])
        self.assertEqual(cloud.calls, [('vm-stop', False), ('vm-stop', True)])
        self.assertFalse(os.path.exists(self.state))
        self.assertTrue(os.path.exists(rep['report_path']))
        self.assertEqual(cloud.uploaded[0][0], 'campus-reports')
        self.assertLessEqual(rep['metrics']['detect_s'], 4)
        self.assertEqual(rep['metrics']['errors_after_detect'], 0)

    def test_refuses_non_app_role(self):
        cloud = FakeCloud(self.clock, role='db')
        with self.assertRaises(cc.Refused):
            self.run_exp(scenario(), cloud)
        self.assertEqual(cloud.calls, [])
        self.assertFalse(os.path.exists(self.state))

    def test_refuses_missing_role(self):
        cloud = FakeCloud(self.clock, role=None)
        with self.assertRaises(cc.Refused):
            self.run_exp(scenario(), cloud)
        self.assertEqual(cloud.calls, [])

    def test_refuses_duration_over_cap(self):
        with self.assertRaises(cc.Refused):
            cc.validate(scenario(duration_s=301))
        with self.assertRaises(cc.Refused):
            cc.validate(scenario(duration_s=0))
        cc.validate(scenario(duration_s=300))

    def test_refuses_unknown_action_and_missing_pool(self):
        with self.assertRaises(cc.Refused):
            cc.validate(scenario(action='delete-vm'))
        sc = scenario()
        sc['target'] = {'server': 'x'}
        with self.assertRaises(cc.Refused):
            cc.validate(sc)

    def test_refuses_when_state_exists(self):
        os.makedirs(os.path.dirname(self.state))
        with open(self.state, 'w', encoding='utf-8') as f:
            f.write('{}')
        cloud = FakeCloud(self.clock)
        with self.assertRaises(cc.Refused):
            self.run_exp(scenario(), cloud)
        self.assertEqual(cloud.calls, [])

    def test_refuses_when_member_not_unique(self):
        cloud = FakeCloud(self.clock, members=[])
        with self.assertRaises(cc.Refused):
            self.run_exp(scenario(), cloud)
        self.assertEqual(cloud.calls, [])

    def test_aborts_and_reverts_early_on_error_rate(self):
        cloud = FakeCloud(self.clock)
        rep = self.run_exp(scenario(stop_if={'error_rate_gt': 0.2}), cloud, errors_after_fault=True)
        self.assertEqual(rep['verdict'], 'ABORTED')
        self.assertIn('ti le loi', rep['aborted_reason'])
        self.assertEqual(cloud.calls[-1], ('vm-stop', True))
        self.assertLess(cloud.revert_t - cloud.fault_t, 45)
        self.assertFalse(os.path.exists(self.state))

    def test_fault_command_failure_still_reverts(self):
        cloud = FakeCloud(self.clock, fault_rc=1)
        rep = self.run_exp(scenario(), cloud)
        self.assertEqual(rep['verdict'], 'ABORTED')
        self.assertEqual(cloud.calls, [('vm-stop', False), ('vm-stop', True)])

    def test_exception_in_loop_still_reverts_and_clears_state(self):
        cloud = FakeCloud(self.clock)
        with self.assertRaises(RuntimeError):
            self.run_exp(scenario(), cloud, boom=True)
        self.assertEqual(cloud.calls[-1], ('vm-stop', True))
        self.assertFalse(os.path.exists(self.state))

    def test_failed_revert_keeps_state_and_revert_command_retries(self):
        cloud = FakeCloud(self.clock, revert_rc=1)
        rep = self.run_exp(scenario(), cloud)
        self.assertNotEqual(rep['verdict'], 'PASS')
        self.assertTrue(os.path.exists(self.state))
        ok_cloud = FakeCloud(self.clock)
        rc, out, st = cc.revert_from_state(ok_cloud, self.state)
        self.assertEqual(rc, 0)
        self.assertEqual(ok_cloud.calls, [('vm-stop', True)])
        self.assertFalse(os.path.exists(self.state))
        self.assertIsNone(cc.revert_from_state(ok_cloud, self.state))

    def test_port_and_member_actions_use_right_commands(self):
        for action in ('member-disable', 'port-disable'):
            cloud = FakeCloud(self.clock)
            ctx = cc.resolve(cloud, scenario(action=action))
            self.assertEqual(ctx['member_id'], 'm-1')
            if action == 'port-disable':
                self.assertEqual(ctx['port_id'], 'port-1')

    def test_analyze_numbers(self):
        probes = [(100 + i * 0.25, 200, 'chaos-lab-1' if i % 2 else 'chaos-lab-2') for i in range(0, 40)]
        probes += [(110 + i * 0.25, 200, 'chaos-lab-2') for i in range(0, 120)]
        probes += [(140 + i * 0.25, 200, 'chaos-lab-1' if i % 2 else 'chaos-lab-2') for i in range(0, 40)]
        probes.sort()
        probes.append((115.0, 0, ''))
        probes.sort()
        statuses = [(100, 'ONLINE', 2), (112.5, 'ERROR', 1), (141.5, 'ONLINE', 2)]
        m = cc.analyze(probes, statuses, 110.0, 135.0, 'chaos-lab-1')
        self.assertEqual(m['detect_s'], 2.5)
        self.assertEqual(m['recover_status_s'], 6.5)
        self.assertEqual(m['errors_in_fault'], 1)
        self.assertEqual(m['errors_after_detect'], 1)  # probe loi @115 sau 112.5+2 -> tinh la loi sau phat hien
        self.assertEqual(m['target_resp_after_detect'], 0)
        self.assertAlmostEqual(m['target_back_s'], 5.25, delta=0.06)  # lam tron 1 chu so

    def test_check_stop_no_online_members(self):
        sc = scenario()
        statuses = [(1000.0, 'ONLINE', 2), (1011.0, 'ERROR', 0)]
        self.assertIn('khong con member ONLINE', cc.check_stop([], statuses, sc, 1010.0, 1012.0))
        self.assertIsNone(cc.check_stop([], [(1011.0, 'ERROR', 1)], sc, 1010.0, 1012.0))

    def test_g_is_tolerant_of_column_names(self):
        self.assertEqual(cc.g({'Operating Status': 'ONLINE'}, 'operating_status'), 'ONLINE')
        self.assertEqual(cc.g({'ID': 'x'}, 'id'), 'x')
        self.assertIsNone(cc.g({'a': 1}, 'b'))


class CloudParsing(unittest.TestCase):
    def mk(self, mapping):
        def runner(args):
            key = ' '.join(args)
            for k, v in mapping.items():
                if key.startswith(k):
                    return 0, json.dumps(v), ''
            return 1, '', 'khong co: ' + key
        return cc.Cloud('x', runner=runner)

    def test_server_props_as_string_or_dict(self):
        c = self.mk({'server show s1': {'id': 'i', 'name': 's1', 'status': 'ACTIVE',
                                        'properties': "campus_role='app'", 'addresses': "campus-net=10.20.0.5"}})
        s = c.server('s1')
        self.assertEqual((s['props'], s['ip']), ({'campus_role': 'app'}, '10.20.0.5'))
        c2 = self.mk({'server show s2': {'id': 'i', 'properties': {'campus_role': 'db'},
                                         'addresses': {'campus-net': ['10.20.0.9']}}})
        s2 = c2.server('s2')
        self.assertEqual((s2['props'], s2['ip']), ({'campus_role': 'db'}, '10.20.0.9'))

    def test_members_and_port(self):
        c = self.mk({'loadbalancer member list p': [{'id': 'a', 'name': 'm1', 'address': '10.20.0.5', 'operating_status': 'ONLINE'}],
                     'port list --server s': [{'ID': 'p1', 'Name': 'x'}]})
        self.assertEqual(c.members('p')[0]['status'], 'ONLINE')
        self.assertEqual(c.port_of('s'), 'p1')

    def test_apply_builds_expected_commands(self):
        seen = []
        c = cc.Cloud('x', runner=lambda a: (seen.append(a) or (0, '', '')))
        ctx = {'server_id': 'S', 'pool': 'P', 'member_id': 'M', 'port_id': 'PT'}
        for action in cc.ACTIONS:
            c.apply(action, ctx)
            c.apply(action, ctx, revert=True)
        self.assertEqual(seen[0], ['server', 'stop', 'S'])
        self.assertEqual(seen[1], ['server', 'start', 'S'])
        self.assertEqual(seen[2], ['loadbalancer', 'member', 'set', '--disable', 'P', 'M'])
        self.assertEqual(seen[3], ['loadbalancer', 'member', 'set', '--enable', 'P', 'M'])
        self.assertEqual(seen[4], ['port', 'set', '--disable', 'PT'])
        self.assertEqual(seen[5], ['port', 'set', '--enable', 'PT'])


if __name__ == '__main__':
    unittest.main()
