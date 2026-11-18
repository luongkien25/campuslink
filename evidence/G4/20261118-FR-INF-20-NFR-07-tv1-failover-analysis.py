"""failover-analysis.py - TV1, 18/11/2026. Chi doc CSV; khong ket noi cloud.
Chia CSV luot failover 10 RPS (FR-INF-20/NFR-07, #66) theo cac moc thuc te TV2 bao (UTC, lan dau quan sat qua API).
Chay: python -I failover-analysis.py <duong dan CSV>
Quy uoc runner: status 599 = timeout/loi ket noi phia may phat (timeout 10 s); 5xx that la 500..598.
p95 tinh theo cach cua workload goc: phan tu int(n*0.95) cua redirect 302 da sap xep.
"""
import csv
import statistics
import sys
from datetime import datetime

MARKS = {  # TV2, 18/11/2026, UTC
    'stop_cmd': '14:57:27.063046',
    'nova_shutoff': '14:57:31.261210',
    'lb_member_a_error': '14:57:36.529516',
    'start_cmd': '15:02:28.479184',
    'nova_active': '15:02:40.644345',
    'both_online': '15:03:19.474286',
}


def U(s):
    return datetime.fromisoformat('2026-11-18T' + s + '+00:00')


def tm(r):
    return datetime.fromisoformat(r['timestamp_utc'].replace('Z', '+00:00'))


def pct(lat, p):
    return lat[min(len(lat) - 1, int(len(lat) * p))]


rows = list(csv.DictReader(open(sys.argv[1], encoding='utf-8', newline='')))
st = [r for r in rows if r['phase'] == 'steady']
T0, END = min(tm(r) for r in st), max(tm(r) for r in st)   # CSV ghi theo thoi diem HOAN THANH, nen dong dau/cuoi khong phai som/muon nhat
m = {k: U(v) for k, v in MARKS.items()}
print('rows=%d steady=%d T0(request steady som nhat)=%s last=%s' % (
    len(rows), len(st), T0.strftime('%H:%M:%S.%f')[:-3], END.strftime('%H:%M:%S.%f')[:-3]))
wins = [
    ('1 truoc (T0 -> lenh dung)', T0, m['stop_cmd']),
    ('2 lenh dung -> LB bao A ERROR', m['stop_cmd'], m['lb_member_a_error']),
    ('3 A tat, LB da loai A', m['lb_member_a_error'], m['start_cmd']),
    ('4 lenh bat -> 2 member ONLINE', m['start_cmd'], m['both_online']),
    ('5 sau (2 member ONLINE -> het)', m['both_online'], END),
]
for name, a, b in wins:
    last = name[0] == '5'
    rs = [r for r in st if a <= tm(r) <= b] if last else [r for r in st if a <= tm(r) < b]
    lat = sorted(float(r['latency_ms']) for r in rs if r['request_type'] == 'redirect' and r['http_status'] == '302')
    to = sum(r['http_status'] == '599' for r in rs)
    s5 = sum(500 <= int(r['http_status']) < 599 for r in rs)
    print('%-32s %6.1fs n=%4d 302=%4d 5xx=%d timeout=%d p50=%5.0f p95=%5.0f max=%6.0f ms' % (
        name, (b - a).total_seconds(), len(rs), sum(r['http_status'] == '302' for r in rs), s5, to,
        statistics.median(lat), pct(lat, .95), max(lat)))
print('--- timeout (599) va thoi diem bat dau request')
for r in st:
    if r['http_status'] == '599':
        print('  %s %+.1fs so voi lenh dung, %s, %.0f ms' % (
            tm(r).strftime('%H:%M:%S.%f')[:-3], (tm(r) - m['stop_cmd']).total_seconds(), r['request_type'], float(r['latency_ms'])))


def slow(a, b):
    return sum(1 for r in st if a <= tm(r) < b and r['request_type'] == 'redirect'
               and r['http_status'] == '302' and float(r['latency_ms']) > 3000)


sb, sd = slow(T0, m['stop_cmd']), slow(m['stop_cmd'], m['both_online'])
print('redirect >3000 ms moi 60 s: truoc lenh dung=%.1f, tu lenh dung den 2 member ONLINE=%.1f' % (
    sb / (m['stop_cmd'] - T0).total_seconds() * 60,
    sd / (m['both_online'] - m['stop_cmd']).total_seconds() * 60))
print('request bat dau trong [lenh dung, LB bao ERROR): %d' % sum(1 for r in st if m['stop_cmd'] <= tm(r) < m['lb_member_a_error']))
print('khoang: dung->Nova SHUTOFF %.1fs; dung->LB ERROR %.1fs; bat->Nova ACTIVE %.1fs; bat->2 member ONLINE %.1fs' % (
    (m['nova_shutoff'] - m['stop_cmd']).total_seconds(), (m['lb_member_a_error'] - m['stop_cmd']).total_seconds(),
    (m['nova_active'] - m['start_cmd']).total_seconds(), (m['both_online'] - m['start_cmd']).total_seconds()))
a_off = [r for r in st if m['stop_cmd'] <= tm(r) < m['start_cmd']]
print('A tat (lenh dung -> lenh bat, %.1fs): n=%d timeout=%d (%.3f%%)' % (
    (m['start_cmd'] - m['stop_cmd']).total_seconds(), len(a_off), sum(r['http_status'] == '599' for r in a_off),
    sum(r['http_status'] == '599' for r in a_off) * 100.0 / len(a_off)))
