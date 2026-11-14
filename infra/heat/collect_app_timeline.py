"""Tong hop moc UTC da thu tu Heat/guest/probe; khong suy ACTIVE thanh ready."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path

MILESTONES = ('vm_active','local_ready','signal_ack','wait_complete','member_active','first_request')


def summarize(events):
    instances = {}
    for row in events:
        if set(row) != {'instance_id','event','utc'} or row['event'] not in MILESTONES:
            raise ValueError('invalid-event')
        stamp = datetime.fromisoformat(row['utc'].replace('Z','+00:00'))
        if stamp.utcoffset() != timedelta(0):
            raise ValueError('utc-required')
        vm = instances.setdefault(row['instance_id'], {})
        if row['event'] in vm:
            raise ValueError('duplicate-milestone')
        vm[row['event']] = stamp
    result = {}; passed = bool(instances)
    for vm, stamps in instances.items():
        complete = all(k in stamps for k in MILESTONES)
        # Server co the hoan tat WC truoc khi client nhan HTTP ACK; hai moc nay
        # khong tao quan he truoc/sau. Chi kiem cac canh nhan qua cua readiness gate.
        edges = (('vm_active','local_ready'),('local_ready','signal_ack'),
                 ('local_ready','wait_complete'),('wait_complete','member_active'),
                 ('member_active','first_request'))
        ordered = complete and all(stamps[a] <= stamps[b] for a,b in edges)
        passed = passed and ordered
        result[vm] = dict(passed=bool(ordered),
                         utc={k:v.isoformat() for k,v in stamps.items()},
                         active_to_request_seconds=(stamps['first_request']-stamps['vm_active']).total_seconds() if complete else None)
    return dict(passed=passed, instances=result)


def main():
    parser = argparse.ArgumentParser(description='Validate normalized per-VM UTC timeline (no raw log bodies)')
    parser.add_argument('events', type=Path)
    args = parser.parse_args()
    try:
        result = summarize(json.loads(args.events.read_text()))
    except (ValueError, TypeError, KeyError, OSError):
        print('FAIL: invalid normalized timeline')
        return 1
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
