"""Probe Shlink that bang TCP moi; Request ID doi chieu guest logs da loc."""
import argparse
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import re
import socket
import ssl
import time
from urllib.parse import urlsplit


def sample(url, count=60, host=None, *, path='/rest/v3/short-urls', redirect_target=None, timeout=5):
    parts = urlsplit(url)
    if (parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ('','/') or not 1 <= count <= 10000
            or not 0 < timeout <= 30 or not path.startswith('/') or any(c.isspace() for c in path)):
        raise ValueError('invalid-probe-input')
    host = host or parts.hostname
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', host):
        raise ValueError('invalid-host')
    rows = []; ids = set()
    for _ in range(count):
        connection = (http.client.HTTPSConnection(parts.hostname, parts.port, timeout=timeout,
                                                  context=ssl.create_default_context())
                      if parts.scheme == 'https' else http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout))
        row = dict(utc=datetime.now(timezone.utc).isoformat(), status=None, request_id=None, passed=False)
        started = time.monotonic()
        try:
            connection.request('GET', path, headers={'Host':host,'Connection':'close'})
            response = connection.getresponse()
            request_id = response.getheader('X-Request-ID')
            if request_id and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', request_id):
                request_id = None
            row.update(status=response.status, request_id=request_id)
            if redirect_target is not None:
                row['passed'] = response.status == 302 and response.getheader('Location') == redirect_target
            else:
                row['passed'] = response.status == 401 and request_id is not None and request_id not in ids
            if request_id:
                ids.add(request_id)
            # Body khong can cho probe; khong theo Location, khong log body/header khac.
            response.close()
        except (OSError, http.client.HTTPException):
            row['error'] = 'connection-or-http-error'
        finally:
            connection.close()
        row['elapsed_seconds'] = round(time.monotonic()-started, 6)
        rows.append(row)
    return dict(passed=all(r['passed'] for r in rows), mode='redirect' if redirect_target else 'auth-deny', requests=rows)


def correlate(request_ids, per_vm_logs, expected_guests):
    expected_guests = set(expected_guests)
    counts = {vm:0 for vm in sorted(expected_guests)}
    errors = []
    if not request_ids or len(set(request_ids)) != len(request_ids) or not expected_guests:
        errors.append('empty-or-duplicate-input')
    for request_id in request_ids:
        hits = [vm for vm, ids in per_vm_logs.items() if request_id in ids]
        if len(hits) != 1 or hits[0] not in expected_guests:
            errors.append('missing-or-ambiguous-request')
        else:
            counts[hits[0]] += 1
    if any(count == 0 for count in counts.values()):
        errors.append('backend-without-hit')
    return dict(passed=not errors, counts=counts, errors=errors)


def main():
    parser = argparse.ArgumentParser(description='Shlink native traffic probe; no API key')
    parser.add_argument('--url'); parser.add_argument('--host')
    parser.add_argument('--report',type=Path,help='Correlate a saved auth-deny report; never send new requests')
    parser.add_argument('--count', type=int, default=60); parser.add_argument('--path', default='/rest/v3/short-urls')
    parser.add_argument('--redirect-target')
    parser.add_argument('--guest-request-ids', type=Path, help='JSON map VM UUID -> filtered Request ID list')
    parser.add_argument('--expect-guest', action='append', default=[])
    args = parser.parse_args()
    try:
        if args.report:
            if args.url or args.host or args.redirect_target or not args.guest_request_ids or not args.expect_guest:
                raise ValueError('invalid-report-mode')
            report = json.loads(args.report.read_text())
            if (not isinstance(report,dict) or set(report) != {'passed','mode','requests'}
                    or report['mode'] != 'auth-deny' or type(report['passed']) is not bool
                    or not isinstance(report['requests'],list)):
                raise ValueError('invalid-saved-report')
            for row in report['requests']:
                if (not isinstance(row,dict) or set(row) - {'utc','status','request_id','passed','elapsed_seconds','error'}
                        or type(row.get('passed')) is not bool
                        or row.get('status') != 401 or not isinstance(row.get('request_id'),str)
                        or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',row['request_id'])):
                    raise ValueError('invalid-saved-request')
            report['passed'] = report['passed'] and all(r['passed'] for r in report['requests'])
        else:
            if not args.url or not args.host:
                raise ValueError('url-host-required')
            report = sample(args.url, args.count, args.host, path=args.path, redirect_target=args.redirect_target)
        if args.guest_request_ids:
            mapping = correlate([r['request_id'] for r in report['requests']],
                                json.loads(args.guest_request_ids.read_text()), args.expect_guest)
            report['backends'] = mapping
            report['passed'] = report['passed'] and mapping['passed']
    except (ValueError, TypeError, KeyError, OSError):
        print('FAIL: invalid probe inputs')
        return 1
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
