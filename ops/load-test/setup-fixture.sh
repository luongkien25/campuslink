#!/usr/bin/env bash
# setup-fixture.sh - Tao short URL fixture truoc phien do
# Chay 1 lan truoc workload.sh. Luu slug vao credentials.env.
# KHONG commit credentials.env.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRED_FILE="${SCRIPT_DIR}/credentials.env"
source "$CRED_FILE"

ADMIN="${SHLINK_ADMIN:-https://s.44-198-215-187.sslip.io}"
API_KEY="${SHLINK_API_KEY}"

create_slug() {
  local slug="$1" url="$2"
  echo "Tao slug: $slug -> $url"
  curl -sf -X POST \
    -H "X-Api-Key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"longUrl\":\"${url}\",\"customSlug\":\"${slug}\",\"tags\":[\"load-test\"]}" \
    "${ADMIN}/rest/v3/short-urls" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  OK:', d.get('shortCode','?'), '->', d.get('longUrl','?'))"
}

create_slug "tv4fix1" "https://example.com/campuslink-fixture-1"
create_slug "tv4fix2" "https://example.com/campuslink-fixture-2"
create_slug "tv4fix3" "https://example.com/campuslink-fixture-3"

echo ""
echo "Xong. Cap nhat FIXTURE_SHORT_CODES trong credentials.env:"
echo "  FIXTURE_SHORT_CODES=\"tv4fix1 tv4fix2 tv4fix3\""
