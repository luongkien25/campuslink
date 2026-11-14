"""Kiem snapshot CPU da loc; khong ket noi cloud, khong doan don vi rate."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import uuid


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError('utc-required')
    return result


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid-number')
    return value


def window_state(values, kind):
    if kind not in ('high', 'low'):
        raise ValueError('invalid-window-kind')
    periods = 2 if kind == 'high' else 3
    values = values[-periods:]
    if len(values) < periods:
        return 'insufficient data'
    try:
        values = [number(value) for value in values]
    except ValueError:
        return 'insufficient data'
    reached = all(value > 60 for value in values) if kind == 'high' else all(value < 25 for value in values)
    return 'alarm' if reached else 'ok'


def _series(resource, now, max_age_seconds, semantics, project_id):
    if (resource['project_id'].replace('-', '') != project_id
            or resource['group'] != 'campuslink-app' or resource['ended_at'] is not None
            or resource['deleted_at'] is not None
            or type(resource['vcpus']) is not int or resource['vcpus'] <= 0
            or resource['unit'] != 'ns'):
        raise ValueError('resource-contract')
    uuid.UUID(resource['metric_id'])
    policy = resource['archive_policy']
    if (not {'mean', 'rate:mean'} <= set(policy['aggregation_methods'])
            or not any(row['granularity'] == 60 for row in policy['definition'])):
        raise ValueError('archive-policy')
    series = {'mean': {}, 'rate:mean': {}}
    for row in resource['rows']:
        aggregation = row['aggregation']
        if aggregation not in series or row['granularity_seconds'] != 60:
            raise ValueError('aggregation-or-granularity')
        stamp = timestamp(row['timestamp'])
        values = series[aggregation]
        if (stamp in values or (values and stamp <= next(reversed(values)))
                or (now-stamp).total_seconds() < 60):
            raise ValueError('unordered-duplicate-or-incomplete')
        values[stamp] = number(row['value'])
    raw = series['mean']; rate = series['rate:mean']
    stamps = list(raw)
    if len(stamps) < 7 or len(rate) < 6:
        raise ValueError('not-enough-buckets')
    if any((b-a).total_seconds() != 60 for a, b in zip(stamps, stamps[1:])):
        raise ValueError('gapped-series')
    selected = stamps[-6:]
    if (list(rate)[-6:] != selected or (now-stamps[-1]).total_seconds()-60 > max_age_seconds):
        raise ValueError('misaligned-or-stale')
    points = []
    for previous, current in zip(stamps[-7:-1], selected):
        delta = raw[current]-raw[previous]
        number(delta)
        rate_delta = rate[current] * (60 if semantics == 'ns-per-second' else 1)
        if not math.isclose(delta, rate_delta, rel_tol=1e-6, abs_tol=1000):
            raise ValueError('rate-counter-mismatch')
        points.append(delta/(60*1e9*resource['vcpus'])*100)
    return selected, points


def analyze(snapshot, expected_guests, *, now, max_age_seconds, rate_semantics):
    if rate_semantics not in ('delta-ns', 'ns-per-second'):
        raise ValueError('explicit-rate-semantics-required')
    if now.tzinfo is None or now.utcoffset().total_seconds() != 0 or number(max_age_seconds) <= 0:
        raise ValueError('invalid-evaluation-clock')
    result = dict(passed=False, errors=[], instances={}, group_cpu_percent=[],
                  high_state='insufficient data', low_state='insufficient data')
    try:
        project_id = uuid.UUID(snapshot['project_id']).hex
        expected = list(expected_guests)
        for ident in expected:
            uuid.UUID(ident)
        if not expected or len(expected) != len(set(expected)) or snapshot['schema_version'] != 1:
            raise ValueError('snapshot-contract')
        collected = timestamp(snapshot['collected_at_utc'])
        if collected > now or (now-collected).total_seconds() > max_age_seconds:
            raise ValueError('snapshot-clock')
        resources = snapshot['resources']
        ids = [resource['uuid'] for resource in resources]
        if len(ids) != len(set(ids)) or set(ids) != set(expected):
            raise ValueError('resource-set-mismatch')
        all_points = []; shared_stamps = None
        for resource in resources:
            stamps, points = _series(resource, now, max_age_seconds, rate_semantics, project_id)
            if shared_stamps is not None and shared_stamps != stamps:
                raise ValueError('resource-buckets-not-aligned')
            shared_stamps = stamps
            all_points.append(points)
            result['instances'][resource['uuid']] = {'cpu_percent': [round(p, 6) for p in points]}
        group = [sum(bucket)/len(bucket) for bucket in zip(*all_points)]
        result.update(passed=True, group_cpu_percent=[round(p, 6) for p in group],
                      bucket_timestamps=[stamp.isoformat() for stamp in shared_stamps],
                      high_state=window_state(group, 'high'), low_state=window_state(group, 'low'))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, IndexError):
        # Khong dua payload API/secret hay exception text vao ket qua.
        result.update(errors=['invalid-or-insufficient-cpu-snapshot'], instances={})
    return result


def main():
    parser = argparse.ArgumentParser(description='Analyze safe CPU snapshot; not Aodh evidence')
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--expect-guest', action='append', required=True)
    parser.add_argument('--now', required=True, help='UTC evaluation time')
    parser.add_argument('--max-age-seconds', type=float, required=True)
    parser.add_argument('--rate-semantics', choices=('delta-ns', 'ns-per-second'), required=True)
    args = parser.parse_args()
    try:
        if args.snapshot.stat().st_size > 8*1024*1024:
            raise ValueError('oversized')
        report = analyze(json.loads(args.snapshot.read_text()), args.expect_guest,
                         now=timestamp(args.now), max_age_seconds=args.max_age_seconds,
                         rate_semantics=args.rate_semantics)
    except (OSError, ValueError, TypeError):
        print('FAIL: invalid CPU inputs; no source payload printed')
        return 1
    print(json.dumps(report, allow_nan=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
