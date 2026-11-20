#!/usr/bin/env bash
# setup-fixture.sh - Tao hoac xac minh 5 short URL fixture truoc phien do (FR-INF-11, FR-INF-16, NFR-03, NFR-04)
# TV4 so huu. Truyen X-Api-Key qua stdin (curl --config -), khong dua secret len argv.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED_FILE="${SCRIPT_DIR}/credentials.env"

if [[ ! -f "$CRED_FILE" ]]; then
  echo "LOI: Thieu $CRED_FILE (sao chep tu credentials.env.example)" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$CRED_FILE"

ADMIN="${SHLINK_ADMIN:-https://s.44-198-215-187.sslip.io}"

ensure_slug() {
  local slug="$1" url="$2"
  local code body actual_url
  code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST "${ADMIN}/rest/v3/short-urls" \
    -H "Content-Type: application/json" \
    --data "{\"longUrl\":\"${url}\",\"customSlug\":\"${slug}\",\"tags\":[\"campus-open-day\",\"load-test\"]}" \
    --config <(printf 'header = "X-Api-Key: %s"\n' "$SHLINK_API_KEY"))
  if [[ "$code" != "200" && "$code" != "400" ]]; then
    echo "  [ERROR]   ${slug} -> HTTP ${code}" >&2
    return 1
  fi
  # Xac minh lai longUrl va tags qua GET /rest/v3/short-urls/{slug} (H5 muc 3.1: Shlink tra 400 ca khi trung slug khac dich)
  body=$(curl -sS "${ADMIN}/rest/v3/short-urls/${slug}" \
    --config <(printf 'header = "X-Api-Key: %s"\n' "$SHLINK_API_KEY"))
  actual_url=$(python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d.get("longUrl",""))' <<<"$body" 2>/dev/null || true)
  if [[ "$actual_url" != "$url" ]]; then
    echo "  [MISMATCH] ${slug}: mong doi longUrl='${url}', thuc te='${actual_url:-KHONG_DOC_DUOC}'" >&2
    return 1
  fi
  if [[ "$code" == "200" ]]; then
    echo "  [CREATED]  ${slug} -> ${actual_url}"
  else
    echo "  [VERIFIED] ${slug} -> ${actual_url} (da ton tai, khop dich)"
  fi
}

echo "Khoi tao 5 fixture slugs tren ${ADMIN}..."
ensure_slug "tv4fix1" "https://example.org/campuslink-fixture-1"
ensure_slug "tv4fix2" "https://example.org/campuslink-fixture-2"
ensure_slug "tv4fix3" "https://example.org/campuslink-fixture-3"
ensure_slug "tv4fix4" "https://example.org/campuslink-fixture-4"
ensure_slug "tv4fix5" "https://example.org/campuslink-fixture-5"
echo "Hoan tat. Dam bao FIXTURE_SHORT_CODES=\"tv4fix1 tv4fix2 tv4fix3 tv4fix4 tv4fix5\" trong credentials.env."
