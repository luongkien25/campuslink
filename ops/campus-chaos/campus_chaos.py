#!/usr/bin/env python3
# campus-chaos v0 (FR-INF-24, SRS 1.4, ADR-11): thi nghiem loi co kiem soat tren app VM cua nhom.
# Chi dung thu vien chuan; goi CLI `openstack` (cac lenh da chay that trong chaos-lab.sh, evidence G3 20261112).
# Rao an toan: chi nhan dich co metadata campus_role=app; moi luc mot thi nghiem (tep state); toi da 300 s;
# dung som khi loi vuot nguong hoac khong con member ONLINE; luon hoan tac (finally) va kiem hoan tac bang luu luong that.
# Chua chay tren cum (v0): xem README.md.
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

MAX_DURATION = 300
ACTIONS = ('vm-stop', 'member-disable', 'port-disable')


class Refused(Exception):
    """Thi nghiem bi tu choi truoc khi gay loi (khong dong vao he thong)."""


def g(d, *names):
    """Lay khoa khong phan biet hoa thuong, dau cach va gach duoi (OSC doi ten cot tuy phien ban)."""
    low = {re.sub(r'[ _]', '', str(k)).lower(): v for k, v in d.items()}
    for n in names:
        v = low.get(re.sub(r'[ _]', '', n).lower())
        if v is not None:
            return v
    return None


# ---------------------------------------------------------------- cloud (CLI openstack)
class Cloud:
    def __init__(self, cloud, runner=None):
        self.cloud = cloud
        self.runner = runner or self._run

    def _run(self, args):
        env = dict(os.environ)
        env['OS_CLOUD'] = self.cloud
        p = subprocess.run(['openstack'] + list(args), capture_output=True, text=True, env=env, timeout=180)
        return p.returncode, p.stdout or '', p.stderr or ''

    def cli(self, *args):
        return self.runner(list(args))

    def cli_json(self, *args):
        rc, out, err = self.cli(*args, '-f', 'json')
        if rc != 0:
            raise RuntimeError('openstack %s loi rc=%d: %s' % (' '.join(args[:3]), rc, (err or out)[:200]))
        return json.loads(out)

    def server(self, name):
        d = self.cli_json('server', 'show', name)
        props = g(d, 'properties') or {}
        if isinstance(props, str):
            props = dict(re.findall(r"(\w+)='([^']*)'", props))
        ips = re.findall(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', str(g(d, 'addresses')))
        return {'id': g(d, 'id'), 'name': g(d, 'name') or name, 'status': g(d, 'status'),
                'props': props, 'ip': ips[0] if ips else None}

    def members(self, pool):
        out = []
        for m in self.cli_json('loadbalancer', 'member', 'list', pool):
            out.append({'id': g(m, 'id'), 'name': g(m, 'name'), 'address': g(m, 'address'),
                        'status': g(m, 'operating_status')})
        return out

    def port_of(self, server_id):
        ports = self.cli_json('port', 'list', '--server', server_id)
        return g(ports[0], 'id') if ports else None

    def apply(self, action, ctx, revert=False):
        if action == 'vm-stop':
            args = ['server', 'start' if revert else 'stop', ctx['server_id']]
        elif action == 'member-disable':
            args = ['loadbalancer', 'member', 'set', '--enable' if revert else '--disable', ctx['pool'], ctx['member_id']]
        elif action == 'port-disable':
            args = ['port', 'set', '--enable' if revert else '--disable', ctx['port_id']]
        else:
            raise Refused('hanh dong khong ho tro: %s' % action)
        rc, out, err = self.cli(*args)
        return rc, (out + err).strip()[:200]

    def upload(self, container, path, name):
        rc, out, err = self.cli('object', 'create', container, path, '--name', name)
        return rc == 0, (out + err).strip()[:200]


# ---------------------------------------------------------------- lay mau luu luong va trang thai LB
class Sampler:
    """Probe HTTP ~rate lan/s va doc trang thai member LB; chay trong thread rieng."""

    def __init__(self, cloud, pool, member_id, url, rate, timeout):
        self.cloud, self.pool, self.member_id = cloud, pool, member_id
        self.url, self.rate, self.timeout = url, rate, timeout
        self._probes, self._status = [], []
        self._stop = threading.Event()
        self._threads = []

    def _probe_loop(self):
        while not self._stop.is_set():
            t, code, body = time.time(), 0, ''
            try:
                with urllib.request.urlopen(self.url, timeout=self.timeout) as r:
                    code = r.status
                    body = r.read(256).decode('utf-8', 'replace').strip()
            except urllib.error.HTTPError as e:
                code = e.code
            except Exception:
                code = 0
            self._probes.append((t, code, body))
            self._stop.wait(1.0 / self.rate)

    def _status_loop(self):
        while not self._stop.is_set():
            t = time.time()
            try:
                ms = self.cloud.members(self.pool)
                mine = [m['status'] for m in ms if m['id'] == self.member_id]
                self._status.append((t, mine[0] if mine else '?', sum(1 for m in ms if m['status'] == 'ONLINE')))
            except Exception:
                self._status.append((t, '?', -1))
            self._stop.wait(0.5)

    def start(self):
        for fn in (self._probe_loop, self._status_loop):
            th = threading.Thread(target=fn, daemon=True)
            th.start()
            self._threads.append(th)

    def stop(self):
        self._stop.set()
        for th in self._threads:
            th.join(timeout=10)

    def probes(self):
        return list(self._probes)

    def statuses(self):
        return list(self._status)


# ---------------------------------------------------------------- logic thuan (kiem thu duoc khong can cum)
def validate(sc):
    for k in ('name', 'action'):
        if not sc.get(k):
            raise Refused('thieu truong %s' % k)
    if sc['action'] not in ACTIONS:
        raise Refused('hanh dong phai la mot trong %s' % (ACTIONS,))
    t = sc.get('target') or {}
    if not t.get('server') or not t.get('pool'):
        raise Refused('thieu target.server hoac target.pool')
    if not (sc.get('probe') or {}).get('url'):
        raise Refused('thieu probe.url')
    d = sc.get('duration_s', 45)
    if not isinstance(d, (int, float)) or d < 1 or d > MAX_DURATION:
        raise Refused('duration_s phai tu 1 den %d' % MAX_DURATION)


def resolve(cloud, sc):
    """Tra ngu canh dich; tu choi neu khong phai app VM cua nhom. Khong gay loi gi."""
    t = sc['target']
    srv = cloud.server(t['server'])
    role = (srv.get('props') or {}).get('campus_role')
    if role != 'app':
        raise Refused('dich %s co campus_role=%r, chi nhan campus_role=app' % (t['server'], role))
    if not srv.get('ip'):
        raise Refused('khong doc duoc dia chi IP cua %s' % t['server'])
    mem = [m for m in cloud.members(t['pool']) if m['address'] == srv['ip']]
    if len(mem) != 1:
        raise Refused('phai co dung 1 member dia chi %s trong pool %s (thay %d)' % (srv['ip'], t['pool'], len(mem)))
    ctx = {'server': srv['name'], 'server_id': srv['id'], 'ip': srv['ip'], 'pool': t['pool'],
           'member_id': mem[0]['id'], 'status_before': srv['status']}
    if sc['action'] == 'port-disable':
        port = cloud.port_of(srv['id'])
        if not port:
            raise Refused('khong tim thay port cua %s' % t['server'])
        ctx['port_id'] = port
    return ctx


def check_stop(probes, statuses, sc, t0, now):
    """Tra ly do dung som (chuoi) hoac None. Chi xet sau khi gay loi."""
    stop = sc.get('stop_if') or {}
    win = float(stop.get('window_s', 5))
    recent = [p for p in probes if p[0] >= max(t0, now - win)]
    thr = stop.get('error_rate_gt', 0.2)
    if len(recent) >= int(stop.get('min_probes', 8)):
        rate = sum(1 for p in recent if p[1] != 200) / len(recent)
        if rate > thr:
            return 'ti le loi %.0f%% trong %gs vuot nguong %.0f%%' % (rate * 100, win, thr * 100)
    online = [s for s in statuses if s[0] >= t0 and s[2] >= 0]
    if online and online[-1][2] < int(stop.get('online_members_lt', 1)):
        return 'khong con member ONLINE (con %d)' % online[-1][2]
    return None


def analyze(probes, statuses, t0, t1, marker):
    """Do phat hien, loi, hoi phuc tu mau probe (t, ma, than) va trang thai (t, trang-thai-dich, so-online)."""
    detect = next((s[0] - t0 for s in statuses if s[0] > t0 and s[1] not in ('ONLINE', '?')), None)
    recover = next((s[0] - t1 for s in statuses if s[0] > t1 and s[1] == 'ONLINE'), None)
    inwin = [p for p in probes if t0 <= p[0] <= t1]
    after = (lambda p: detect is not None and p[0] >= t0 + detect + 2)
    is_t = (lambda p: bool(marker) and marker in p[2])
    back = next((p[0] - t1 for p in probes if p[0] > t1 and p[1] == 200 and (is_t(p) or not marker)), None)
    return {
        'detect_s': None if detect is None else round(detect, 1),
        'recover_status_s': None if recover is None else round(recover, 1),
        'target_back_s': None if back is None else round(back, 1),
        'probes_in_fault': len(inwin),
        'errors_in_fault': sum(1 for p in inwin if p[1] != 200),
        'errors_after_detect': sum(1 for p in inwin if p[1] != 200 and after(p)),
        'target_resp_after_detect': sum(1 for p in inwin if is_t(p) and after(p)) if marker else None,
    }


def verdict(sc, m, frc, rrc, aborted):
    th = sc.get('hypothesis') or {}
    checks = {
        'lenh_gay_loi_ok': frc == 0,
        'hoan_tac_ok': rrc == 0,
        'phat_hien_trong_han': m['detect_s'] is not None and m['detect_s'] <= th.get('detect_within_s', 15),
        'khong_loi_sau_phat_hien': m['errors_after_detect'] <= th.get('max_errors_after_detect', 0)
        and not m['target_resp_after_detect'],
        'dich_tro_lai': m['target_back_s'] is not None
        and m['target_back_s'] <= th.get('recover_within_s', 150),
    }
    if aborted:
        return 'ABORTED', checks
    return ('PASS' if all(checks.values()) else 'FAIL'), checks


def now_utc():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def run_experiment(sc, cloud, sampler_factory, state_path, report_dir, clock=time.time, sleep=time.sleep, upload=True):
    validate(sc)
    if os.path.exists(state_path):
        raise Refused('dang co thi nghiem hoac lan truoc bi ngat (%s); chay: campus-chaos revert' % state_path)
    ctx = resolve(cloud, sc)
    os.makedirs(os.path.dirname(state_path) or '.', exist_ok=True)
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump({'name': sc['name'], 'action': sc['action'], 'ctx': ctx, 'started': clock()}, f)
    probe = sc['probe']
    sampler = sampler_factory(ctx, probe)
    marker = probe.get('marker')
    duration = float(sc.get('duration_s', 45))
    applied = reverted = False
    aborted = None
    frc = rrc = None
    t0 = t1 = None
    sampler.start()
    try:
        sleep(float(sc.get('baseline_s', 10)))
        t0 = clock()
        applied = True
        frc, fout = cloud.apply(sc['action'], ctx)
        if frc != 0:
            aborted = 'lenh gay loi that bai: %s' % fout
        while aborted is None and clock() - t0 < duration:
            sleep(1)
            aborted = check_stop(sampler.probes(), sampler.statuses(), sc, t0, clock())
    finally:
        t1 = clock()
        if applied:
            rrc, rout = cloud.apply(sc['action'], ctx, revert=True)
            reverted = rrc == 0
        if reverted or not applied:
            # da hoan tac (hoac chua gay loi gi): khong con can tep state; neu hoan tac that bai thi GIU de `revert` thu lai
            if os.path.exists(state_path):
                os.remove(state_path)
        if reverted:
            wait = float((sc.get('hypothesis') or {}).get('recover_within_s', 150))
            while clock() - t1 < wait:
                st = [s for s in sampler.statuses() if s[0] > t1]
                back = [p for p in sampler.probes() if p[0] > t1 and p[1] == 200 and (not marker or marker in p[2])]
                if st and st[-1][1] == 'ONLINE' and back:
                    break
                sleep(2)
            sleep(2)
        sampler.stop()
    m = analyze(sampler.probes(), sampler.statuses(), t0, t1, marker)
    v, checks = verdict(sc, m, frc, rrc, aborted)
    report = {'scenario': sc, 'target': ctx, 'verdict': v, 'checks': checks, 'metrics': m,
              'aborted_reason': aborted, 'fault_rc': frc, 'revert_rc': rrc,
              't0': t0, 't1': t1, 'finished_utc': now_utc()}
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, '%s-%s.json' % (now_utc(), sc['name']))
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    report['report_path'] = path
    if upload:
        ok, msg = cloud.upload((sc.get('report') or {}).get('swift_container', 'campus-reports'), path,
                               'chaos/' + os.path.basename(path))
        report['uploaded'] = ok
        if not ok:
            print('CANH BAO: khong ghi duoc bao cao len Swift: %s' % msg, file=sys.stderr)
    return report


def revert_from_state(cloud, state_path):
    if not os.path.exists(state_path):
        return None
    with open(state_path, encoding='utf-8') as f:
        st = json.load(f)
    rc, out = cloud.apply(st['action'], st['ctx'], revert=True)
    if rc == 0:
        os.remove(state_path)
    return rc, out, st


def load_scenario(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()
    if path.endswith('.json'):
        return json.loads(text)
    try:
        import yaml
    except ImportError:
        raise SystemExit('can PyYAML de doc kich ban .yaml (hoac dung .json)')
    return yaml.safe_load(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description='campus-chaos v0: thi nghiem loi co kiem soat (FR-INF-24)')
    ap.add_argument('--cloud', default=os.environ.get('CHAOS_CLOUD', 'campus-chaos'))
    ap.add_argument('--state-dir', default=os.environ.get('CHAOS_STATE_DIR', '/var/lib/campus-chaos'))
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('scenario')
    r.add_argument('--dry-run', action='store_true', help='chi kiem va in ke hoach, khong gay loi')
    r.add_argument('--no-upload', action='store_true')
    sub.add_parser('revert')
    sub.add_parser('status')
    a = ap.parse_args(argv)
    state = os.path.join(a.state_dir, 'state.json')
    cloud = Cloud(a.cloud)
    if a.cmd == 'status':
        print(open(state, encoding='utf-8').read() if os.path.exists(state) else 'khong co thi nghiem dang chay')
        return 0
    if a.cmd == 'revert':
        res = revert_from_state(cloud, state)
        if res is None:
            print('khong co state, khong co gi de hoan tac')
            return 0
        print('hoan tac rc=%d %s' % (res[0], res[1]))
        return 0 if res[0] == 0 else 1
    sc = load_scenario(a.scenario)
    try:
        validate(sc)
        if a.dry_run:
            ctx = resolve(cloud, sc)
            print('DRY-RUN hop le. Se gay: %s len %s (member %s). Khong gay loi gi.' % (sc['action'], ctx['server'], ctx['member_id']))
            return 0
        pr = sc['probe']
        factory = lambda ctx, p: Sampler(cloud, ctx['pool'], ctx['member_id'], p['url'],
                                         float(p.get('rate_per_s', 4)), float(p.get('timeout_s', 1)))
        rep = run_experiment(sc, cloud, factory, state, os.path.join(a.state_dir, 'reports'), upload=not a.no_upload)
    except Refused as e:
        print('TU CHOI: %s' % e, file=sys.stderr)
        return 2
    print(json.dumps({'verdict': rep['verdict'], 'checks': rep['checks'], 'metrics': rep['metrics'],
                      'aborted_reason': rep['aborted_reason'], 'report': rep['report_path']}, ensure_ascii=False, indent=2))
    return 0 if rep['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
