#!/usr/bin/env python3
"""
workload.py - Bo phat tai Shlink core theo profile NFR-03 (FR-INF-11, NFR-01..04, NFR-06).
TV4 so huu. Chi dung thu vien chuan Python 3, doc credential tu file rieng (khong qua argv),
ghi raw CSV kem timestamp UTC, HTTP status, latency (ms) va X-Request-Id de doi chieu log backend.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import json
import pathlib
import random
import ssl
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_env_file(path: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def send_one(
    opener: urllib.request.OpenerDirector,
    req_type: str,
    slug: str,
    base_url: str,
    admin_url: str,
    api_key: str,
    timeout_s: float = 10.0,
) -> tuple[str, str, str, int, float, str, str]:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    t0 = time.perf_counter()
    headers = {"User-Agent": "campuslink-tv4-workload/1.0"}
    data = None
    method = "GET"

    if req_type == "redirect":
        url = f"{base_url.rstrip('/')}/{slug}"
    elif req_type == "visits":
        url = f"{admin_url.rstrip('/')}/rest/v3/short-urls/{slug}/visits?itemsPerPage=20"
        headers["X-Api-Key"] = api_key
    else:
        url = f"{admin_url.rstrip('/')}/rest/v3/short-urls"
        method = "POST"
        headers["X-Api-Key"] = api_key
        headers["Content-Type"] = "application/json"
        payload = {
            "longUrl": f"https://example.org/load-test?t={int(time.time()*1000)}&r={random.randint(1000,9999)}",
            "tags": ["load-test"],
        }
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    status = 0
    req_id = ""
    location = ""
    try:
        with opener.open(req, timeout=timeout_s) as resp:
            status = resp.status
            req_id = resp.headers.get("X-Request-Id", "") or ""
            location = resp.headers.get("Location", "") or ""
            resp.read(256)
    except urllib.error.HTTPError as exc:
        status = exc.code
        if exc.headers:
            req_id = exc.headers.get("X-Request-Id", "") or ""
            location = exc.headers.get("Location", "") or ""
    except Exception:
        status = 599  # timeout hoac loi ket noi

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return ts, req_type, slug, status, latency_ms, req_id, location


def run_phase(
    phase_name: str,
    rps: int,
    duration_s: int,
    workers: int,
    slugs: list[str],
    base_url: str,
    admin_url: str,
    api_key: str,
    csv_writer: csv.writer,
    csv_lock: threading.Lock,
    warmup_only_redirect: bool = False,
) -> list[tuple[str, int, float]]:
    ctx = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        NoRedirectHandler(),
    )
    results: list[tuple[str, int, float]] = []
    total_requests = max(1, rps * duration_s)
    interval = 1.0 / max(1, rps)
    start_monotonic = time.perf_counter()

    print(
        f"[{dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%SZ')}] "
        f"Bat dau {phase_name}: {rps} RPS x {duration_s}s ({total_requests} requests)..."
    )

    def task(idx: int) -> None:
        target_time = start_monotonic + idx * interval
        sleep_s = target_time - time.perf_counter()
        if sleep_s > 0:
            time.sleep(sleep_s)
        slug = random.choice(slugs)
        if warmup_only_redirect:
            req_type = "redirect"
        else:
            roll = idx % 20
            if roll < 16:
                req_type = "redirect"   # 80%
            elif roll < 19:
                req_type = "visits"     # 15%
            else:
                req_type = "create"     # 5%
        row = send_one(opener, req_type, slug, base_url, admin_url, api_key)
        with csv_lock:
            csv_writer.writerow([phase_name, *row])
            results.append((row[1], row[3], row[4]))

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(task, i) for i in range(total_requests)]
        concurrent.futures.wait(futures)

    print(
        f"[{dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%SZ')}] "
        f"Ket thuc {phase_name}."
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="CampusLink NFR-03 Workload Generator")
    parser.add_argument("--rps", type=int, default=30, help="Target RPS in steady state (10, 30, 60)")
    parser.add_argument("--warmup", type=int, default=120, help="Warm-up duration in seconds (default: 120)")
    parser.add_argument("--steady", type=int, default=300, help="Steady duration in seconds (default: 300)")
    parser.add_argument("--workers", type=int, default=32, help="Concurrent worker threads")
    parser.add_argument(
        "--cred-file",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent / "credentials.env",
        help="Path to credentials.env",
    )
    args = parser.parse_args()

    if not args.cred_file.is_file():
        print(f"LOI: Khong tim thay file credential: {args.cred_file}", file=sys.stderr)
        return 1

    env = load_env_file(args.cred_file)
    api_key = env.get("SHLINK_API_KEY", "")
    base_url = env.get("SHLINK_BASE", "https://s.44-198-215-187.sslip.io")
    admin_url = env.get("SHLINK_ADMIN", base_url)
    slugs = [s for s in env.get("FIXTURE_SHORT_CODES", "").split() if s and not s.startswith("REPLACE_")]

    if not api_key or api_key == "REPLACE_SHLINK_API_KEY":
        print("LOI: SHLINK_API_KEY chua duoc dien trong credentials.env", file=sys.stderr)
        return 1
    if not slugs:
        print("LOI: FIXTURE_SHORT_CODES rong hoac chua thay the REPLACE_ trong credentials.env", file=sys.stderr)
        return 1

    log_dir = pathlib.Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts_tag = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = log_dir / f"{ts_tag}-workload-{args.rps}rps-raw.csv"
    csv_lock = threading.Lock()

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["phase", "timestamp_utc", "request_type", "slug", "http_status", "latency_ms", "request_id", "location"]
        )
        if args.warmup > 0:
            run_phase(
                "warmup",
                min(10, args.rps),
                args.warmup,
                args.workers,
                slugs,
                base_url,
                admin_url,
                api_key,
                writer,
                csv_lock,
                warmup_only_redirect=True,
            )
        steady_rows = run_phase(
            "steady",
            args.rps,
            args.steady,
            args.workers,
            slugs,
            base_url,
            admin_url,
            api_key,
            writer,
            csv_lock,
            warmup_only_redirect=False,
        )

    redirect_latencies = sorted(lat for rtype, status, lat in steady_rows if rtype == "redirect" and status == 302)
    errors_5xx = sum(1 for _, status, _ in steady_rows if status >= 500 or status == 0)
    total = len(steady_rows)

    print("\n======================================================")
    print(f"TOM TAT STEADY-STATE ({args.rps} RPS, {args.steady}s)")
    print("======================================================")
    print(f"Raw CSV          : {csv_path}")
    print(f"Tong so request  : {total}")
    if redirect_latencies:
        p50 = statistics.median(redirect_latencies)
        p95 = redirect_latencies[min(len(redirect_latencies) - 1, int(len(redirect_latencies) * 0.95))]
        print(f"Redirect 302 OK  : {len(redirect_latencies)}")
        print(f"Redirect p50     : {p50:.2f} ms")
        print(f"Redirect p95     : {p95:.2f} ms (NFR-01 muc tieu <= 500 ms)")
    if total:
        err_pct = (errors_5xx / total) * 100.0
        print(f"Loi 5xx/timeout  : {errors_5xx}/{total} ({err_pct:.2f}%, NFR-02 muc tieu < 1%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
