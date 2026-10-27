#!/usr/bin/env python3
"""Lay mau HTTP stub qua ket noi moi; tra exit 1 neu thieu backend hoac co loi."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from http.client import HTTPException
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, url):
        return None


def sample(url, expected, requests, timeout):
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("URL phai la HTTP(S), khong co credential, query hay fragment")
    if (not expected or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", label)
                            for label in expected)):
        raise ValueError("Can it nhat mot nhan backend hop le")
    if (not isinstance(requests, int) or not 1 <= requests <= 10000
            or not math.isfinite(timeout) or not 0 < timeout <= 30):
        raise ValueError("requests trong [1, 10000], timeout trong (0, 30] giay")
    started = datetime.now(timezone.utc).isoformat()
    counts, errors = Counter(), Counter()
    # Moi lan open tao mot HTTPConnection moi; khong dung proxy tu moi truong.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    for _ in range(requests):
        request = Request(url, headers={"Connection": "close", "Cache-Control": "no-cache"})
        try:
            with opener.open(request, timeout=timeout) as response:
                if response.status != 200:
                    errors[f"HTTP_{response.status}"] += 1
                    continue
                body = response.read(4097)
                if len(body) > 4096:
                    errors["invalid_payload"] += 1
                    continue
                # read(amt) co the tra JSON hop le du Content-Length chua du.
                length = response.headers.get("Content-Length")
                if not response.chunked and length is not None and len(body) != int(length):
                    errors["connection_error"] += 1
                    continue
                data = json.loads(body)
                if (not isinstance(data, dict) or data.get("service") != "campuslink-lb-stub"
                        or not isinstance(data.get("backend"), str)
                        or data["backend"] not in expected):
                    errors["invalid_payload"] += 1
                    continue
                counts[data["backend"]] += 1
        except HTTPError as error:
            errors[f"HTTP_{error.code}"] += 1
            error.close()
        except (URLError, OSError, HTTPException):
            errors["connection_error"] += 1
        except (ValueError, UnicodeError):
            errors["invalid_payload"] += 1
    missing = sorted(expected - counts.keys())
    return {
        "service": "campuslink-lb-stub-sample",
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "requests": requests,
        "counts": dict(counts),
        "errors": dict(errors),
        "missing": missing,
        "passed": not missing and not errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--expect", action="append", required=True)
    parser.add_argument("--requests", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=3)
    args = parser.parse_args()
    try:
        report = sample(args.url, set(args.expect), args.requests, args.timeout)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
