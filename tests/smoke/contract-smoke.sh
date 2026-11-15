#!/usr/bin/env bash
# contract-smoke.sh - Kiem thu hop dong REST API Shlink 5.1.8 & Ingress TLS (FR-APP-01..12, FR-INF-06, NFR-10, NFR-14)
# TV4 so huu. Doc SHLINK_API_KEY tu file credentials.env va truyen qua stdin (curl --config -), KHONG lo key tren argv.

set -euo pipefail

CRED_FILE="${1:-$(dirname "${BASH_SOURCE[0]}")/../load/credentials.env}"
if [[ ! -f "$CRED_FILE" ]]; then
  echo "LOI: Khong tim thay file credential: $CRED_FILE" >&2
  echo "Hay sao chep tu tests/load/credentials.env.example va dien SHLINK_API_KEY." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$CRED_FILE"

SHORT_BASE="${SHLINK_BASE:-https://s.44-198-215-187.sslip.io}"
ADMIN_UI="${SHLINK_ADMIN_UI:-https://admin.44-198-215-187.sslip.io}"

if [[ -z "${SHLINK_API_KEY:-}" || "${SHLINK_API_KEY}" == "REPLACE_SHLINK_API_KEY" ]]; then
  echo "LOI: SHLINK_API_KEY chua duoc dien trong $CRED_FILE" >&2
  exit 1
fi

PASS=0
FAIL=0
RUN_SLUG="tv4-smoke-$(date -u +%Y%m%dT%H%M%SZ)"

check_eq() {
  local req_id="$1" desc="$2" expected="$3" actual="$4"
  if [[ "$actual" == "$expected" ]]; then
    echo "PASS  ${req_id}  ${desc} (=${actual})"
    PASS=$((PASS + 1))
  else
    echo "FAIL  ${req_id}  ${desc} (expected=${expected}, actual=${actual})"
    FAIL=$((FAIL + 1))
  fi
}

curl_api_status() {
  local method="$1" url="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -sS -o /dev/null -w "%{http_code}" -X "$method" "$url" \
      -H "Content-Type: application/json" \
      --data "$body" \
      --config <(printf 'header = "X-Api-Key: %s"\n' "$SHLINK_API_KEY")
  else
    curl -sS -o /dev/null -w "%{http_code}" -X "$method" "$url" \
      --config <(printf 'header = "X-Api-Key: %s"\n' "$SHLINK_API_KEY")
  fi
}

echo "== CampusLink Contract Smoke Test ($(date -u +%Y-%m-%dT%H:%M:%SZ)) =="
echo "Target: ${SHORT_BASE} | Admin UI: ${ADMIN_UI}"

# 1. FR-INF-06, FR-APP-11, NFR-10: Health check HTTPS (khong dung -k)
HEALTH_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "${SHORT_BASE}/rest/health")
check_eq "FR-INF-06/FR-APP-11" "GET /rest/health HTTPS (verify cert)" "200" "$HEALTH_CODE"

# 2. FR-APP-09: Web Client SPA tinh va route con khong 404
UI_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "${ADMIN_UI}/")
check_eq "FR-APP-09" "GET admin Web Client root" "200" "$UI_CODE"

# 3. FR-APP-07: Khong key va key sai tra 401
NOKEY_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "${SHORT_BASE}/rest/v3/short-urls")
check_eq "FR-APP-07" "GET /rest/v3/short-urls khong co X-Api-Key" "401" "$NOKEY_CODE"

BADKEY_CODE=$(curl -sS -o /dev/null -w "%{http_code}" -H "X-Api-Key: 00000000-0000-0000-0000-000000000000" "${SHORT_BASE}/rest/v3/short-urls")
check_eq "FR-APP-07" "GET /rest/v3/short-urls voi key sai" "401" "$BADKEY_CODE"

# 4. FR-APP-10: CORS preflight OPTIONS tu origin admin
CORS_ORIGIN=$(curl -sS -D - -o /dev/null -X OPTIONS "${SHORT_BASE}/rest/v3/short-urls" \
  -H "Origin: ${ADMIN_UI}" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: X-Api-Key, Content-Type" \
  | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}' | tail -n 1)
check_eq "FR-APP-10" "CORS Access-Control-Allow-Origin khop admin domain" "${ADMIN_UI}" "$CORS_ORIGIN"

# 5. FR-APP-01: Tao short URL voi customSlug va tag campus-open-day
CREATE_CODE=$(curl_api_status POST "${SHORT_BASE}/rest/v3/short-urls" \
  "{\"longUrl\":\"https://example.org/smoke-init\",\"customSlug\":\"${RUN_SLUG}\",\"tags\":[\"campus-open-day\"]}")
check_eq "FR-APP-01" "POST /rest/v3/short-urls tao slug ${RUN_SLUG}" "200" "$CREATE_CODE"

# 6. FR-APP-12: Tao trung customSlug tra 400
DUP_CODE=$(curl_api_status POST "${SHORT_BASE}/rest/v3/short-urls" \
  "{\"longUrl\":\"https://example.org/smoke-dup\",\"customSlug\":\"${RUN_SLUG}\"}")
check_eq "FR-APP-12" "POST trung slug tra 400 non-unique-slug" "400" "$DUP_CODE"

# 7. FR-APP-02: Redirect 302 + Location dung (khong follow)
REDIR_HEADERS=$(curl -sS -D - -o /dev/null "${SHORT_BASE}/${RUN_SLUG}" | tr -d '\r')
REDIR_STATUS=$(echo "$REDIR_HEADERS" | awk 'NR==1{print $2}')
REDIR_LOC=$(echo "$REDIR_HEADERS" | awk -F': ' 'tolower($1)=="location"{print $2}' | tail -n 1)
check_eq "FR-APP-02" "GET /${RUN_SLUG} status 302" "302" "$REDIR_STATUS"
check_eq "FR-APP-02" "GET /${RUN_SLUG} Location ban dau" "https://example.org/smoke-init" "$REDIR_LOC"

# 8. FR-APP-03: PATCH doi longUrl
PATCH_CODE=$(curl_api_status PATCH "${SHORT_BASE}/rest/v3/short-urls/${RUN_SLUG}" \
  "{\"longUrl\":\"https://example.org/smoke-updated\"}")
check_eq "FR-APP-03" "PATCH /rest/v3/short-urls/${RUN_SLUG}" "200" "$PATCH_CODE"

REDIR_LOC2=$(curl -sS -D - -o /dev/null "${SHORT_BASE}/${RUN_SLUG}" | tr -d '\r' | awk -F': ' 'tolower($1)=="location"{print $2}' | tail -n 1)
check_eq "FR-APP-03" "GET /${RUN_SLUG} Location sau PATCH" "https://example.org/smoke-updated" "$REDIR_LOC2"

# 9. FR-APP-04 & FR-APP-05: Visits va Tag stats
sleep 2
VISITS_CODE=$(curl_api_status GET "${SHORT_BASE}/rest/v3/short-urls/${RUN_SLUG}/visits")
check_eq "FR-APP-04" "GET /rest/v3/short-urls/${RUN_SLUG}/visits" "200" "$VISITS_CODE"

TAGS_CODE=$(curl_api_status GET "${SHORT_BASE}/rest/v3/tags/stats")
check_eq "FR-APP-05" "GET /rest/v3/tags/stats" "200" "$TAGS_CODE"

# 10. FR-APP-12: Slug khong ton tai tra 404
NOTFOUND_CODE=$(curl -sS -o /dev/null -w "%{http_code}" "${SHORT_BASE}/slug-khong-ton-tai-999999")
check_eq "FR-APP-12" "GET slug khong ton tai tra 404" "404" "$NOTFOUND_CODE"

echo "== Ket qua: PASS=${PASS} FAIL=${FAIL} =="
[[ "$FAIL" -eq 0 ]]
