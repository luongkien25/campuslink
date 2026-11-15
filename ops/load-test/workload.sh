#!/usr/bin/env bash
# workload.sh - Phat tai Shlink core cho phep do autoscaling (FR-INF-11, NFR-03, NFR-06)
# TV4 so huu. Chay tu may ca nhan, khong chay tren campus-a.
#
# Yeu cau:
#   - hey: https://github.com/rakyll/hey  (go install github.com/rakyll/hey@latest)
#   - curl, jq, bc
#   - File credential: ops/load-test/credentials.env (KHONG commit)
#     Noi dung mau: ops/load-test/credentials.env.example
#
# Cach chay:
#   bash ops/load-test/workload.sh [10|30|60]   # RPS muc tieu (mac dinh: 30)
#
# Credential duoc doc tu file, khong qua argv hay bien moi truong shell.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED_FILE="${SCRIPT_DIR}/credentials.env"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOG_DIR"

# --- Kiem tra credential file ---
if [[ ! -f "$CRED_FILE" ]]; then
  echo "LỖII: Thieu file credential: $CRED_FILE"
  echo "Tao tu mau: cp ops/load-test/credentials.env.example ops/load-test/credentials.env"
  exit 1
fi

# shellcheck source=/dev/null
source "$CRED_FILE"
# Bien can co trong credentials.env:
#   SHLINK_API_KEY=<api key>
#   SHLINK_BASE=https://s.44-198-215-187.sslip.io
#   SHLINK_ADMIN=https://s.44-198-215-187.sslip.io   # endpoint REST
#   FIXTURE_SHORT_CODES="abc123 def456 ghi789"       # cach nhau boi dau cach

# --- Tham so ---
TARGET_RPS="${1:-30}"
WARMUP_DURATION=120     # 2 phut warm-up
STEADY_DURATION=300     # 5 phut steady-state moi muc
CONCURRENCY=10          # so goroutine dong thoi (hey -c)
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG_PREFIX="${LOG_DIR}/${TIMESTAMP}-workload-${TARGET_RPS}rps"

echo "======================================================"
echo "CampusLink Workload - FR-INF-11 / NFR-03"
echo "RPS muc tieu : ${TARGET_RPS}"
echo "Warm-up      : ${WARMUP_DURATION}s"
echo "Steady-state : ${STEADY_DURATION}s"
echo "Log prefix   : ${LOG_PREFIX}"
echo "======================================================"
echo ""

# --- Chuan bi fixture short codes ---
read -r -a SHORT_CODES <<< "$FIXTURE_SHORT_CODES"
if [[ ${#SHORT_CODES[@]} -eq 0 ]]; then
  echo "LOI: FIXTURE_SHORT_CODES rong trong credentials.env"
  exit 1
fi

# Chon short code dai dien (slug nong, slug nguoi dung khac nhau)
HOT_SLUG="${SHORT_CODES[0]}"
VISIT_SLUG="${SHORT_CODES[0]}"

echo "[$(date -u +%H:%M:%SZ)] Bat dau warm-up ${WARMUP_DURATION}s..."

# === WARM-UP: 10 RPS ===
hey -z "${WARMUP_DURATION}s" \
    -q 10 \
    -c "${CONCURRENCY}" \
    -disable-redirects \
    -o csv \
    "${SHLINK_BASE}/${HOT_SLUG}" \
    >> "${LOG_PREFIX}-warmup.csv" 2>&1 &
WARMUP_PID=$!
wait "$WARMUP_PID"
echo "[$(date -u +%H:%M:%SZ)] Warm-up xong."

echo "[$(date -u +%H:%M:%SZ)] Bat dau steady-state ${TARGET_RPS} RPS trong ${STEADY_DURATION}s..."
echo "timestamp_utc,http_status,latency_ms,request_id" > "${LOG_PREFIX}-steady.csv"

# === STEADY-STATE: profile NFR-03 ===
# 80% GET /{shortCode}, 15% GET visits, 5% POST short-url
# Chay song song 3 hey voi ty le RPS phu hop
RPS_REDIRECT=$(echo "$TARGET_RPS * 80 / 100" | bc)
RPS_VISITS=$(echo "$TARGET_RPS * 15 / 100" | bc)
RPS_CREATE=$(echo "$TARGET_RPS * 5 / 100" | bc)
# Dam bao toi thieu 1
[[ "$RPS_REDIRECT" -lt 1 ]] && RPS_REDIRECT=1
[[ "$RPS_VISITS" -lt 1 ]] && RPS_VISITS=1
[[ "$RPS_CREATE" -lt 1 ]] && RPS_CREATE=1

# 80% redirect
hey -z "${STEADY_DURATION}s" \
    -q "${RPS_REDIRECT}" \
    -c "${CONCURRENCY}" \
    -disable-redirects \
    -o csv \
    "${SHLINK_BASE}/${HOT_SLUG}" \
    > "${LOG_PREFIX}-redirect.csv" 2>&1 &
PID_REDIRECT=$!

# 15% visits
hey -z "${STEADY_DURATION}s" \
    -q "${RPS_VISITS}" \
    -c 3 \
    -H "X-Api-Key: ${SHLINK_API_KEY}" \
    -o csv \
    "${SHLINK_ADMIN}/rest/v3/short-urls/${VISIT_SLUG}/visits" \
    > "${LOG_PREFIX}-visits.csv" 2>&1 &
PID_VISITS=$!

# 5% POST create short-url (endpoint tao link moi)
hey -z "${STEADY_DURATION}s" \
    -q "${RPS_CREATE}" \
    -c 2 \
    -m POST \
    -H "Content-Type: application/json" \
    -H "X-Api-Key: ${SHLINK_API_KEY}" \
    -d '{"longUrl":"https://example.com/load-test","tags":["load-test"]}' \
    -o csv \
    "${SHLINK_ADMIN}/rest/v3/short-urls" \
    > "${LOG_PREFIX}-create.csv" 2>&1 &
PID_CREATE=$!

echo "[$(date -u +%H:%M:%SZ)] Dang chay tai (Ctrl+C de dung sach)..."
echo "  PID redirect=${PID_REDIRECT} visits=${PID_VISITS} create=${PID_CREATE}"

# Trap Ctrl+C: dung sach
cleanup() {
  echo ""
  echo "[$(date -u +%H:%M:%SZ)] Nhan tin hieu dung - giet cac tien trinh tai..."
  kill "$PID_REDIRECT" "$PID_VISITS" "$PID_CREATE" 2>/dev/null || true
  echo "[$(date -u +%H:%M:%SZ)] Da dung."
}
trap cleanup INT TERM

wait "$PID_REDIRECT" "$PID_VISITS" "$PID_CREATE"
echo "[$(date -u +%H:%M:%SZ)] Steady-state ket thuc."

# === TOM TAT ===
echo ""
echo "======================================================"
echo "TOM TAT - ${TARGET_RPS} RPS"
echo "======================================================"
echo "File log:"
ls -lh "${LOG_PREFIX}"*.csv 2>/dev/null || true

# Tinh toan tu csv redirect
if [[ -f "${LOG_PREFIX}-redirect.csv" ]]; then
  echo ""
  echo "--- Redirect (80%) ---"
  # CSV cua hey: response-time,dns-lookup,connection-establishment,...,status-code
  # Tinh p50/p95 va ti le 2xx
  python3 - <<PYEOF
import csv, sys, statistics, pathlib
f = "${LOG_PREFIX}-redirect.csv"
rows = []
errors = 0
with open(f) as fh:
    rd = csv.DictReader(fh)
    for r in rd:
        try:
            rows.append(float(r['response-time']) * 1000)  # ms
            if not r['status-code'].startswith('2') and not r['status-code'].startswith('3'):
                errors += 1
        except Exception:
            pass
if rows:
    print(f"  Tong request : {len(rows)}")
    print(f"  p50 latency  : {statistics.median(rows):.1f} ms")
    rows.sort()
    p95 = rows[int(len(rows)*0.95)]
    print(f"  p95 latency  : {p95:.1f} ms (NFR-01: <=500ms)")
    print(f"  Ti le loi    : {errors/len(rows)*100:.2f}% (NFR-02: <1%)")
PYEOF
fi

echo ""
echo "Log day du tai: ${LOG_DIR}/"
echo "Ghi log nay vao evidence/G5/ sau khi phoi hop voi TV2."
