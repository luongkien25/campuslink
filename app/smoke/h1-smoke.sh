#!/usr/bin/env bash
# CampusLink - smoke hop dong H1 (SRS muc 3.1, 4.1, 4.3). TV3.
# Chay duoc cho Compose local (mac dinh) va cho cum (dat bien moi truong).
# Chi in PASS/FAIL va gia tri khong nhay cam; API key doc tu file, khong in ra.
#
# Bien:
#   A, B              URL goc cua 2 replica (B co the trung A neu chi co 1)
#   SHORT_BASE        tien to shortUrl mong doi (local: http://localhost:18080; cum: https://s.<CAMPUS_DOMAIN>)
#   KEY_ADMIN_FILE    file chua key admin ung dung
#   KEY_UA_FILE, KEY_UB_FILE   2 key --author-only (FR-APP-08)
#   ADMIN_ORIGIN      origin Web Client (FR-APP-10)
#   DB_STOP_CMD, DB_START_CMD  lenh dung/bat PostgreSQL de thu 503 (bo trong thi bo qua phep thu)
#   REDIS_PING_CMD    lenh PING Redis co xac thuc, phai in PONG (bo trong thi bo qua)
#   VISITS_N          so GET de dem visit (mac dinh 20)
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
sec="$here/../compose/secrets"
A=${A:-http://127.0.0.1:18080}
B=${B:-http://127.0.0.1:18081}
SHORT_BASE=${SHORT_BASE:-http://localhost:18080}
KEY_ADMIN_FILE=${KEY_ADMIN_FILE:-$sec/api_key_tv3-admin}
KEY_UA_FILE=${KEY_UA_FILE:-$sec/api_key_tv3-donvi-a}
KEY_UB_FILE=${KEY_UB_FILE:-$sec/api_key_tv3-donvi-b}
ADMIN_ORIGIN=${ADMIN_ORIGIN:-https://admin.44-198-215-187.sslip.io}
VISITS_N=${VISITS_N:-20}
UA='Mozilla/5.0 (X11; Linux x86_64) campuslink-smoke'

# Key KHONG nam tren argv cua curl (ps thay duoc tren VM dung chung): ghi header vao file 0600 trong thu muc mktemp
# bang printf (builtin), curl doc bang -H @file. Bien hk_* la DUONG DAN file header, khong phai key.
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
hdr() { local f; f=$(umask 077; mktemp "$work/h.XXXXXX"); printf 'X-Api-Key: %s\n' "$(tr -d '\r\n' < "$1")" > "$f"; echo "$f"; }
hk_admin=$(hdr "$KEY_ADMIN_FILE"); hk_ua=$(hdr "$KEY_UA_FILE"); hk_ub=$(hdr "$KEY_UB_FILE")
run_id=$(date -u +%Y%m%dT%H%M%SZ)
slug="tv3-smoke-${run_id,,}"
tag=campus-smoke
fails=0

check() { # ma, mo ta, mong doi, thuc te
  if [[ $3 == "$4" ]]; then echo "PASS  $1  $2  (=$4)"; else echo "FAIL  $1  $2  (mong doi $3, thuc te $4)"; fails=$((fails+1)); fi
}
code() { curl -sS -o /dev/null -w '%{http_code}' "$@"; }
api() { # file header key, method, url, [body]
  local k=$1 m=$2 u=$3; shift 3
  curl -sS -X "$m" "$u" -H @"$k" -H 'Content-Type: application/json' "$@"
}
visits_total() { api "$hk_admin" GET "$A/rest/v3/short-urls/$1/visits?itemsPerPage=1" | jq -r '.visits.pagination.totalItems'; }

echo "run_id=$run_id A=$A B=$B slug=$slug"
echo "== health"
check FR-APP-11 "health A" "200 pass" "$(curl -sS -w ' %{http_code}' "$A/rest/health" | sed -E 's/.*"status":"([a-z]+)".* ([0-9]+)$/\2 \1/')"
check FR-APP-11 "health B" "200 pass" "$(curl -sS -w ' %{http_code}' "$B/rest/health" | sed -E 's/.*"status":"([a-z]+)".* ([0-9]+)$/\2 \1/')"
if [[ -n ${REDIS_PING_CMD:-} ]]; then
  check FR-INF-09 "Redis PING co xac thuc" PONG "$(bash -c "$REDIS_PING_CMD" 2>&1 | tr -d '\r')"
fi

echo "== API key"
check FR-APP-07 "POST khong key" 401 "$(code -X POST "$A/rest/v3/short-urls" -H 'Content-Type: application/json' --data '{"longUrl":"https://example.org/"}')"
check FR-APP-07 "POST key sai" 401 "$(code -X POST "$A/rest/v3/short-urls" -H 'X-Api-Key: 00000000-0000-0000-0000-000000000000' -H 'Content-Type: application/json' --data '{"longUrl":"https://example.org/"}')"

echo "== tao, trung slug, 404"
body=$(printf '{"longUrl":"https://example.org/?campus=%s","customSlug":"%s","tags":["%s"]}' "$run_id" "$slug" "$tag")
resp=$(api "$hk_admin" POST "$A/rest/v3/short-urls" --data "$body" -w '\n%{http_code}')
check FR-APP-01 "POST tao link" 200 "$(tail -n1 <<<"$resp")"
check FR-APP-01 "shortUrl dung domain" "$SHORT_BASE/$slug" "$(head -n -1 <<<"$resp" | jq -r .shortUrl)"
resp=$(api "$hk_admin" POST "$A/rest/v3/short-urls" --data "$body" -w '\n%{http_code}')
check FR-APP-12 "tao trung slug" "400 non-unique-slug" "$(tail -n1 <<<"$resp") $(head -n -1 <<<"$resp" | jq -r '.type' | sed 's|.*/||')"
check FR-APP-12 "slug khong ton tai" 404 "$(code -A "$UA" "$A/khong-ton-tai-$run_id")"

echo "== redirect, sua, nhat quan 2 replica"
expected_get=0
loc() { curl -sS -o /dev/null -A "$UA" -w '%{http_code} %{redirect_url}' "$1/$slug"; }
check FR-APP-02 "GET qua A" "302 https://example.org/?campus=$run_id" "$(loc "$A")"; expected_get=$((expected_get+1))
check FR-APP-02 "GET qua B (cache truoc khi sua)" "302 https://example.org/?campus=$run_id" "$(loc "$B")"; expected_get=$((expected_get+1))
check FR-APP-03 "PATCH qua A" 200 "$(api "$hk_admin" PATCH "$A/rest/v3/short-urls/$slug" --data "{\"longUrl\":\"https://example.org/?campus=updated-$run_id\"}" -o /dev/null -w '%{http_code}')"
check NFR-12 "GET qua B sau PATCH o A" "302 https://example.org/?campus=updated-$run_id" "$(loc "$B")"; expected_get=$((expected_get+1))
check NFR-12 "GET qua A sau PATCH" "302 https://example.org/?campus=updated-$run_id" "$(loc "$A")"; expected_get=$((expected_get+1))

echo "== visit (task nen ghi bat dong bo)"
for i in $(seq 1 "$VISITS_N"); do
  if (( i % 2 )); then curl -sS -o /dev/null -A "$UA" "$A/$slug"; else curl -sS -o /dev/null -A "$UA" "$B/$slug"; fi
done
expected_get=$((expected_get+VISITS_N))
t0=$(date +%s.%N); got=0
for _ in $(seq 1 60); do got=$(visits_total "$slug"); [[ $got == "$expected_get" ]] && break; sleep 0.5; done
lag=$(echo "$(date +%s.%N) - $t0" | bc)
check FR-APP-04 "so visit = so GET" "$expected_get" "$got"
echo "INFO  FR-APP-04  visit du sau ${lag}s ke tu GET cuoi"

echo "== tag"
tag_line=$(api "$hk_admin" GET "$A/rest/v3/tags/stats" | jq -r --arg t "$tag" '.tags.data[] | select(.tag==$t) | "\(.shortUrlsCount>0) \(.visitsSummary.total>0)"')
check FR-APP-05 "tags/stats co $tag, co link va visit" "true true" "$tag_line"

echo "== author-only"
slug_a="${slug}-donvi-a"
check FR-APP-08 "key don vi A tao link" 200 "$(api "$hk_ua" POST "$A/rest/v3/short-urls" --data "{\"longUrl\":\"https://example.org/a\",\"customSlug\":\"$slug_a\"}" -o /dev/null -w '%{http_code}')"
check FR-APP-08 "key A doc link cua A" 200 "$(api "$hk_ua" GET "$A/rest/v3/short-urls/$slug_a" -o /dev/null -w '%{http_code}')"
check FR-APP-08 "key B doc link cua A" 404 "$(api "$hk_ub" GET "$B/rest/v3/short-urls/$slug_a" -o /dev/null -w '%{http_code}')"
check FR-APP-08 "danh sach cua key B khong co link A" 0 "$(api "$hk_ub" GET "$A/rest/v3/short-urls?searchTerm=$slug_a" | jq '.shortUrls.data | length')"
check FR-APP-08 "key B sua link cua A" 404 "$(api "$hk_ub" PATCH "$A/rest/v3/short-urls/$slug_a" --data '{"longUrl":"https://example.org/hack"}' -o /dev/null -w '%{http_code}')"

echo "== CORS"
pre=$(curl -sS -o /dev/null -D - -X OPTIONS "$A/rest/v3/short-urls" -H "Origin: $ADMIN_ORIGIN" \
  -H 'Access-Control-Request-Method: POST' -H 'Access-Control-Request-Headers: x-api-key, content-type' | tr -d '\r')
check FR-APP-10 "preflight allow-origin" "$ADMIN_ORIGIN" "$(grep -i '^access-control-allow-origin:' <<<"$pre" | cut -d' ' -f2)"
check FR-APP-10 "preflight cho x-api-key" yes "$(grep -i '^access-control-allow-headers:' <<<"$pre" | grep -qi 'x-api-key' && echo yes || echo no)"
pre=$(curl -sS -o /dev/null -D - -X OPTIONS "$A/rest/v3/short-urls" -H 'Origin: https://evil.example' \
  -H 'Access-Control-Request-Method: POST' | tr -d '\r')
check FR-APP-10 "origin la khong duoc allow" none "$(grep -i '^access-control-allow-origin:' <<<"$pre" | cut -d' ' -f2 | grep . || echo none)"

if [[ -n ${DB_STOP_CMD:-} && -n ${DB_START_CMD:-} ]]; then
  echo "== DB loi"
  bash -c "$DB_STOP_CMD" >/dev/null 2>&1
  sleep 3
  check FR-APP-11 "health khi DB dung" "503 fail" "$(curl -sS -m 10 -w ' %{http_code}' "$A/rest/health" | sed -E 's/.*"status":"([a-z]+)".* ([0-9]+)$/\2 \1/')"
  bash -c "$DB_START_CMD" >/dev/null 2>&1
  ok=""; for _ in $(seq 1 30); do [[ $(code "$A/rest/health") == 200 ]] && ok=200 && break; sleep 1; done
  check FR-APP-11 "health sau khi bat lai DB" 200 "${ok:-khong-len}"
  check FR-APP-02 "redirect sau khi DB len lai" "302 https://example.org/?campus=updated-$run_id" "$(loc "$A")"
fi

echo "== ket qua: $fails FAIL"
exit $((fails > 0))
