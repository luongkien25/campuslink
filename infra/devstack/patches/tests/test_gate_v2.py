# Ca thu OFFLINE cho gate v2 cua ADR-12 (aodh-adr12-gate-v2.patch).
# Chay voi ma Aodh THAT o SHA e07aeb6d (da ap v1 + v2) va Gnocchi GIA (mo phong
# ham aggregated() cua Gnocchi 4.7.1: needed_overlap>0 va thieu diem -> 400).
# Khong goi mang, khong cham cum.
#
# Cach chay (tu thu muc BAT KY, KHONG dung trong thu muc clone Aodh):
#   python -I test_gate_v2.py <thu_muc_aodh_da_ap_v1_v2> <file_gnocchi_py_upstream>
# <file_gnocchi_py_upstream> = ban aodh/evaluator/gnocchi.py goc (git show e07aeb6d:...)
# dung cho ca 11 (so voi upstream).
import datetime
import importlib.util
import math
import sys
import unittest
from unittest import mock

AODH_DIR = sys.argv[1] if len(sys.argv) > 1 else None
UPSTREAM_GNOCCHI = sys.argv[2] if len(sys.argv) > 2 else None
if AODH_DIR:
    sys.path.insert(0, AODH_DIR)

from gnocchiclient import exceptions  # noqa: E402
from oslo_utils import timeutils  # noqa: E402

from aodh.evaluator import gnocchi  # noqa: E402
from aodh.evaluator import threshold  # noqa: E402

EPOCH = datetime.datetime(1970, 1, 1)
CPU1 = 60e9  # 100% cua 1 vCPU trong 60 s (ns)
HIGH = dict(comparison_operator='gt', threshold=36e9, evaluation_periods=2,
            aggregation_method='rate:mean', granularity=60, metric='cpu',
            resource_type='instance',
            query='{"and":[{"=":{"server_group":"g"}},{"=":{"ended_at":null}}]}')
LOW = dict(HIGH, comparison_operator='lt', threshold=15e9,
           evaluation_periods=3)


def ts(hhmm, sec=0):
    # moc trong ngay 20/11/2026 (UTC, naive)
    h, m = hhmm.split(':')
    return datetime.datetime(2026, 11, 20, int(h), int(m), sec)


def secs(dt):
    return (dt - EPOCH).total_seconds()


def pct(p):
    return p / 100.0 * CPU1


class FakeGnocchi(object):
    """Gnocchi gia: vms = {ten: {'ended_at': None|dt, 'pts': {dt: rate}}}."""

    def __init__(self, vms):
        self.vms = vms
        self.calls = []

    @property
    def aggregates(self):
        return self

    def fetch(self, operations, granularity, search, resource_type,
              start, stop, needed_overlap):
        self.calls.append(dict(operations=operations, start=start, stop=stop,
                               needed_overlap=needed_overlap))
        agg = operations[1]
        cohort = [v for v in self.vms.values() if v.get('ended_at') is None]
        if not cohort:
            raise exceptions.NotFound(404, 'no resource')
        g = granularity
        start_s = secs(timeutils.normalize_time(
            timeutils.parse_isotime(start))) // g * g
        stop_s = secs(timeutils.normalize_time(timeutils.parse_isotime(stop)))
        series = []
        for v in cohort:
            series.append(dict((secs(t), val) for t, val in v['pts'].items()
                               if start_s <= secs(t) < stop_s))
        times = sorted(set(t for s in series for t in s))
        full = [t for t in times if all(t in s for s in series)]
        if needed_overlap > 0:
            # giong gnocchi/rest/aggregates/processor.py aggregated()
            if not full:
                raise exceptions.BadRequest(400, 'No overlap')
            if len(full) * 100.0 / len(times) < needed_overlap:
                raise exceptions.BadRequest(400, 'Less than overlap')
        out = []
        for t in times:
            vals = [s[t] for s in series if t in s]
            if agg == 'mean':
                val = sum(vals) / len(vals)
            elif agg == 'min':
                val = (float('nan') if any(math.isnan(x) for x in vals)
                       else min(vals))
            else:
                raise AssertionError(agg)
            iso = (EPOCH + datetime.timedelta(seconds=t)).isoformat()
            out.append([iso + '+00:00', float(g), val])
        return {'measures': {'aggregated': out}}


class FakeConf(object):
    additional_ingestion_lag = 0


def make_ev(cls, vms):
    ev = cls.__new__(cls)
    ev.conf = FakeConf()
    ev._gnocchi_client = FakeGnocchi(vms)
    return ev


def run(ev, rule, now):
    """Tra ve (state, stats) hoac ('insufficient', reason)."""
    orig = ev._statistics

    def rec(rule, start, end):
        # ghi lai dau ra cua _statistics (truoc _sanitize) de kiem timestamp
        ev.raw = orig(rule, start, end)
        return ev.raw
    ev._statistics = rec
    ev.raw = None
    try:
        with mock.patch.object(timeutils, 'utcnow', return_value=now):
            r = ev.evaluate_rule(dict(rule))
    except threshold.InsufficientDataError as e:
        return ('insufficient', e.reason)
    state = r[0] if r[0] is not None else 'trend:' + r[1]
    return (state, r[2])


def steady(p, frm='09:50', to='10:00', skip=()):
    out = {}
    t = ts(frm)
    while t <= ts(to):
        if t not in skip:
            out[t] = pct(p)
        t += datetime.timedelta(seconds=60)
    return out


NOW = ts('10:00', 50)  # bucket dong gan nhat = 09:59 (09:59+60+45 <= 10:00:50)
EV = gnocchi.GnocchiAggregationResourcesThresholdEvaluator


class TestGateV2(unittest.TestCase):

    def test_01_hai_vm_on_dinh_high_alarm(self):
        ev = make_ev(EV, {'a': {'pts': steady(70)}, 'b': {'pts': steady(65)}})
        state, stats = run(ev, HIGH, NOW)
        self.assertEqual('alarm', state)
        self.assertEqual(2, len(stats))
        c = ev._gnocchi_client.calls
        self.assertEqual(['mean', 'min'], [x['operations'][1] for x in c])
        self.assertEqual(['metric', 'cpu', 'rate:mean'], c[0]['operations'][2])
        self.assertEqual('2026-11-20T09:58:00', c[0]['start'])
        self.assertEqual('2026-11-20T10:00:00', c[0]['stop'])
        self.assertEqual(100, c[0]['needed_overlap'])

    def test_02_bucket_dang_ghi_bi_loai(self):
        # 10:00 dang ghi: chi VM a co diem, gia tri am (kieu 15/11)
        a = steady(70, to='09:59')
        a[ts('10:00')] = pct(-35)
        ev = make_ev(EV, {'a': {'pts': a}, 'b': {'pts': steady(70, to='09:59')}})
        state, stats = run(ev, HIGH, NOW)
        self.assertEqual('alarm', state)
        self.assertEqual(['2026-11-20T09:58:00', '2026-11-20T09:59:00'],
                         [s[0] for s in ev.raw])
        # truoc giay :45 cua phut, bucket 09:59 chua du lag -> cua so 09:57-09:58
        ev = make_ev(EV, {'a': {'pts': a}, 'b': {'pts': steady(70, to='09:59')}})
        state, stats = run(ev, HIGH, ts('10:00', 30))
        self.assertEqual(['2026-11-20T09:57:00', '2026-11-20T09:58:00'],
                         [s[0] for s in ev.raw])

    def test_03_thieu_bucket_giua(self):
        gap = (ts('09:58'),)
        ev = make_ev(EV, {'a': {'pts': steady(70, skip=gap)},
                          'b': {'pts': steady(70, skip=gap)}})
        self.assertEqual(('insufficient', 'campus-gate reject=missing_bucket'),
                         run(ev, HIGH, NOW))
        # chi mot VM thieu -> Gnocchi 400 (needed_overlap=100)
        ev = make_ev(EV, {'a': {'pts': steady(70, skip=gap)},
                          'b': {'pts': steady(70)}})
        self.assertEqual(('insufficient', 'campus-gate reject=gnocchi_400'),
                         run(ev, HIGH, NOW))

    def test_04_vm_moi_thieu_rate_toi_khi_du_n(self):
        vms = {'a': {'pts': steady(70, to='10:02')},
               'b': {'pts': steady(70, to='10:02')},
               'c': {'pts': steady(50, frm='09:59', to='10:02')}}
        ev = make_ev(EV, vms)
        self.assertEqual(('insufficient', 'campus-gate reject=gnocchi_400'),
                         run(ev, HIGH, NOW))
        # mot phut sau: cua so 09:59-10:00, VM c du 2 bucket -> danh gia lai
        state, stats = run(ev, HIGH, ts('10:01', 50))
        self.assertEqual('alarm', state)
        self.assertAlmostEqual(pct(190 / 3.0), stats[-1])

    def test_05_counter_reset_am(self):
        b = steady(70)
        b[ts('09:59')] = pct(-50)  # reset counter: rate am
        a = steady(70)  # mean 09:59 = 10% > 0 nen chi min bat duoc
        ev = make_ev(EV, {'a': {'pts': a}, 'b': {'pts': b}})
        self.assertEqual(('insufficient', 'campus-gate reject=negative'),
                         run(ev, HIGH, NOW))

    def test_06_nan_inf(self):
        for bad in (float('nan'), float('inf')):
            b = steady(70)
            b[ts('09:59')] = bad
            ev = make_ev(EV, {'a': {'pts': steady(70)}, 'b': {'pts': b}})
            self.assertEqual(('insufficient', 'campus-gate reject=nonfinite'),
                             run(ev, HIGH, NOW))

    def test_07_diem_cu(self):
        # du lieu dung o 09:58 (<= now - 120 s), khong co bucket 09:59
        ev = make_ev(EV, {'a': {'pts': steady(70, to='09:58')},
                          'b': {'pts': steady(70, to='09:58')}})
        self.assertEqual(('insufficient', 'campus-gate reject=stale'),
                         run(ev, HIGH, NOW))
        # Gnocchi tre hon han: khong co diem nao trong cua so -> 400 No overlap
        ev = make_ev(EV, {'a': {'pts': steady(70, to='09:56')},
                          'b': {'pts': steady(70, to='09:56')}})
        self.assertEqual(('insufficient', 'campus-gate reject=gnocchi_400'),
                         run(ev, HIGH, NOW))

    def test_08_vm_roi_cohort_co_ended_at(self):
        vms = {'a': {'pts': steady(30)}, 'b': {'pts': steady(20)},
               'c': {'pts': steady(2, to='09:57'), 'ended_at': ts('09:58', 5)}}
        ev = make_ev(EV, vms)
        state, stats = run(ev, LOW, NOW)
        self.assertEqual('ok', state)
        self.assertEqual([pct(25)] * 3, stats)

    def test_09_vm_roi_cohort_chua_co_ended_at(self):
        vms = {'a': {'pts': steady(30, to='10:06')},
               'b': {'pts': steady(20, to='10:06')},
               'c': {'pts': steady(2, to='09:57')}}
        ev = make_ev(EV, vms)
        self.assertEqual(('insufficient', 'campus-gate reject=gnocchi_400'),
                         run(ev, LOW, NOW))
        # van ket khi chua co ended_at (mat liveness, an toan: khong co action)
        self.assertEqual('insufficient', run(ev, LOW, ts('10:05', 50))[0])
        vms['c']['ended_at'] = ts('10:06')
        self.assertEqual('ok', run(ev, LOW, ts('10:06', 50))[0])

    def test_10_low_ba_bucket_duoi_25(self):
        ev = make_ev(EV, {'a': {'pts': steady(10)}, 'b': {'pts': steady(12)}})
        state, stats = run(ev, LOW, NOW)
        self.assertEqual('alarm', state)
        self.assertEqual(3, len(stats))

    def test_11_khong_tien_to_rate_giong_upstream(self):
        self.assertTrue(UPSTREAM_GNOCCHI, 'can duong dan gnocchi.py upstream')
        spec = importlib.util.spec_from_file_location('up_gnocchi',
                                                      UPSTREAM_GNOCCHI)
        up = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(up)
        UP = up.GnocchiAggregationResourcesThresholdEvaluator
        rule = dict(HIGH, aggregation_method='mean', threshold=50.0,
                    evaluation_periods=3)
        datasets = [
            {'a': {'pts': steady(70)}, 'b': {'pts': steady(80)}},
            {'a': {'pts': steady(10)}, 'b': {'pts': steady(80, skip=(ts('09:59'),))}},
            {'a': {'pts': steady(70, to='09:58')}},
            {'a': {'pts': {}}},
        ]
        for vms in datasets:
            for now in (NOW, ts('10:00', 5)):
                r_up = run(make_ev(UP, vms), rule, now)
                ev = make_ev(EV, vms)
                r_v2 = run(ev, rule, now)
                self.assertEqual(r_up, r_v2)
                ev_up = make_ev(UP, vms)
                run(ev_up, rule, now)
                self.assertEqual(ev_up._gnocchi_client.calls,
                                 ev._gnocchi_client.calls)
                self.assertEqual(0, ev._gnocchi_client.calls[0]['needed_overlap'])


class FakeAlarm(object):
    # chi cac truong ma evaluate()/_transition_alarm()/_refresh() doc
    def __init__(self, rule, state):
        self.alarm_id = 'a-' + rule['comparison_operator']
        self.project_id = 'p'
        self.rule = dict(rule)
        self.state = state
        self.state_reason = state
        self.repeat_actions = False  # nhu infra/heat/alarms.yaml
        self.time_constraints = []
        self.severity = 'low'


def make_full_ev(cls, vms):
    ev = make_ev(cls, vms)
    ev.conf.record_history = False
    ev.conf.enable_evaluation_results_metrics = False
    ev.storage_conn = mock.Mock()
    ev.notifier = mock.Mock()
    return ev


def window(vals, last='09:59'):
    # N bucket lien tiep ket thuc o bucket dong gan nhat, gia tri % CPU
    t = ts(last) - datetime.timedelta(seconds=60 * (len(vals) - 1))
    out = {}
    for v in vals:
        out[t] = pct(v)
        t += datetime.timedelta(seconds=60)
    return out


def run_full(cls, rule, state, vals, now=NOW):
    """Chay evaluate() (tang tren evaluate_rule): tra (state, refresh_calls)."""
    ev = make_full_ev(cls, {'a': {'pts': window(vals)},
                            'b': {'pts': window(vals)}})
    alarm = FakeAlarm(rule, state)
    with mock.patch.object(ev, '_refresh', wraps=ev._refresh) as spy:
        with mock.patch.object(timeutils, 'utcnow', return_value=now):
            ev.evaluate(alarm)
    return alarm.state, [c.args[1] for c in spy.call_args_list], ev


def load_upstream():
    spec = importlib.util.spec_from_file_location('up_gnocchi2',
                                                  UPSTREAM_GNOCCHI)
    up = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(up)
    return up.GnocchiAggregationResourcesThresholdEvaluator


UNKNOWN = 'insufficient data'


class TestGateV21Evaluate(unittest.TestCase):
    # Ca hoi phuc o tang evaluate() (TV2 review PR #81): tu insufficient data,
    # cua so lan lon KHONG duoc dung trending_state.

    def test_a_insufficient_high_lan_lon_khong_alarm(self):
        state, calls, ev = run_full(EV, HIGH, UNKNOWN, [55, 65])
        self.assertEqual(UNKNOWN, state)
        self.assertEqual([], calls)
        self.assertEqual([], ev.notifier.notify.call_args_list)

    def test_b_insufficient_high_quyet_dinh_alarm(self):
        state, calls, ev = run_full(EV, HIGH, UNKNOWN, [65, 70])
        self.assertEqual(('alarm', ['alarm']), (state, calls))
        self.assertEqual(1, len(ev.notifier.notify.call_args_list))

    def test_c_insufficient_low_lan_lon_khong_alarm(self):
        state, calls, ev = run_full(EV, LOW, UNKNOWN, [30, 30, 20])
        self.assertEqual((UNKNOWN, []), (state, calls))
        self.assertEqual([], ev.notifier.notify.call_args_list)

    def test_d_insufficient_low_quyet_dinh_alarm(self):
        state, calls, ev = run_full(EV, LOW, UNKNOWN, [20, 22, 18])
        self.assertEqual(('alarm', ['alarm']), (state, calls))

    def test_e_insufficient_high_quyet_dinh_khong_vuot_ok(self):
        state, calls, ev = run_full(EV, HIGH, UNKNOWN, [30, 35])
        self.assertEqual(('ok', ['ok']), (state, calls))

    def test_f_ok_lan_lon_giu_ok(self):
        state, calls, ev = run_full(EV, HIGH, 'ok', [55, 65])
        self.assertEqual(('ok', []), (state, calls))
        state, calls, ev = run_full(EV, LOW, 'ok', [30, 30, 20])
        self.assertEqual(('ok', []), (state, calls))

    def test_g_alarm_lan_lon_giu_alarm(self):
        state, calls, ev = run_full(EV, HIGH, 'alarm', [55, 65])
        self.assertEqual(('alarm', []), (state, calls))
        state, calls, ev = run_full(EV, LOW, 'alarm', [30, 30, 20])
        self.assertEqual(('alarm', []), (state, calls))

    def test_h_khong_rate_giong_upstream(self):
        self.assertTrue(UPSTREAM_GNOCCHI, 'can duong dan gnocchi.py upstream')
        UP = load_upstream()
        rule = dict(HIGH, aggregation_method='mean', threshold=pct(60))
        for state0 in (UNKNOWN, 'ok', 'alarm'):
            for vals in ([55, 65], [65, 70], [30, 35], [65, 55]):
                for now in (NOW, ts('10:00', 5)):
                    r_up = run_full(UP, rule, state0, vals, now)
                    r_v2 = run_full(EV, rule, state0, vals, now)
                    self.assertEqual(r_up[:2], r_v2[:2])
                    self.assertEqual(
                        [c.args[1:] for c in
                         r_up[2].notifier.notify.call_args_list],
                        [c.args[1:] for c in
                         r_v2[2].notifier.notify.call_args_list])
        # nhanh trending cua upstream van con voi aggregation khong rate:
        st, calls, ev = run_full(EV, rule, UNKNOWN, [55, 65])
        self.assertEqual(('alarm', ['alarm']), (st, calls))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], '-v'])
