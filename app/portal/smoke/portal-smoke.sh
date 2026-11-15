#!/usr/bin/env bash
# CampusLink - smoke campus-portal MVP (#40 phuong an B) theo cot "Kiem bang" SRS 3.3. TV3.
# Chay tren Compose local sau: ./gen-portal-secrets.sh && docker compose --profile portal up -d --build --wait
# Lan dau tu tao: admin, 2 don vi (key Shlink --author-only), tai khoan unit A/B va viewer A.
# Chi in PASS/FAIL va gia tri khong nhay cam.
# Mat khau va API key KHONG nam tren argv cua curl (ps thay duoc): ghi bang printf (lenh builtin, khong tao
# tien trinh) vao file trong $work (0700), roi curl doc bang --data-urlencode "k@file" va -H @file.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
cd "$here/../../compose"
P=${PORTAL:-http://127.0.0.1:18090}
S=${SHLINK:-http://127.0.0.1:18080}
sec=secrets
run_id=$(date -u +%Y%m%dT%H%M%SZ); rid=${run_id,,}
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
umask 077
sf() { local f; f=$(mktemp "$work/s.XXXXXX"); printf '%s' "$1" > "$f"; echo "$f"; }   # gia tri -> file khong xuong dong
fails=0
check() { if [[ $3 == "$4" ]]; then echo "PASS  $1  $2  (=$4)"; else echo "FAIL  $1  $2  (mong doi $3, thuc te $4)"; fails=$((fails+1)); fi; }
dc() { docker compose --profile portal "$@"; }

# --- dung tai khoan + key (idempotent theo ten) ---
pwfile() { [[ -e $sec/$1 ]] || { umask 077; openssl rand -hex 12 > "$sec/$1"; }; cat "$sec/$1"; }
adm_pw=$(cat "$sec/portal_admin_password")
dc exec -T portal python -m portal.cli create-admin admin <<< "$adm_pw" >/dev/null 2>&1 || true

jar() { echo "$work/$1.jar"; }
csrf() { curl -sS -b "$(jar "$1")" -c "$(jar "$1")" "$P$2" | sed -n 's/.*name="csrf" value="\([^"]*\)".*/\1/p' | head -1; }
login() { # ten, mat khau -> 0 neu vao duoc
  local t; t=$(csrf "$1" /login)
  curl -sS -o /dev/null -b "$(jar "$1")" -c "$(jar "$1")" -w '%{http_code} %{redirect_url}' "$P/login" \
    --data-urlencode "csrf=$t" --data-urlencode "username=$1" --data-urlencode "password@$(sf "$2")"
}
post() { # ai, duong dan, [--data-urlencode k=v ...] -> "code location"
  local who=$1 path=$2; shift 2; local t; t=$(csrf "$who" "${CSRF_PAGE:-/campaigns}")
  curl -sS -o "$work/out" -b "$(jar "$who")" -c "$(jar "$who")" -w '%{http_code} %{redirect_url}' "$P$path" --data-urlencode "csrf=$t" "$@"
}
get() { curl -sS -o "$work/out" -b "$(jar "$1")" -w '%{http_code}' "$P$2"; }
loc() { curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' -A 'Mozilla/5.0 campuslink-portal-smoke' "$1"; }

echo "run_id=$run_id portal=$P shlink=$S"
echo "== healthz"
check SRS-4.6 "healthz portal" "200 pass" "$(curl -sS -w ' %{http_code}' "$P/healthz" | sed -E 's/.*"status":"([a-z]+)".* ([0-9]+)$/\2 \1/')"

echo "== chuan bi (admin tao don vi, tai khoan)"
check FR-APP-13 "admin dang nhap" "303 $P/" "$(login admin "$adm_pw")"
for u in a b; do
  if [[ ! -e $sec/api_key_portal-donvi-$u ]]; then
    dc exec -T shlink shlink api-key:generate --author-only --name="portal-donvi-$u" 2>/dev/null \
      | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1 > "$sec/api_key_portal-donvi-$u"
    chmod 400 "$sec/api_key_portal-donvi-$u"
  fi
  CSRF_PAGE=/admin post admin /admin/units --data-urlencode "name=Don vi $u" --data-urlencode "api_key@$sec/api_key_portal-donvi-$u" >/dev/null
done
uid_a=$(get admin /admin >/dev/null; sed -n 's/.*<option value="\([0-9]*\)">Don vi a<.*/\1/p' "$work/out" | head -1)
uid_b=$(sed -n 's/.*<option value="\([0-9]*\)">Don vi b<.*/\1/p' "$work/out" | head -1)
pa=$(pwfile portal_pw_unit_a); pb=$(pwfile portal_pw_unit_b); pv=$(pwfile portal_pw_viewer_a)
CSRF_PAGE=/admin post admin /admin/users --data-urlencode username=unit-a --data-urlencode "password@$(sf "$pa")" --data-urlencode role=unit --data-urlencode "unit_id=$uid_a" >/dev/null
CSRF_PAGE=/admin post admin /admin/users --data-urlencode username=unit-b --data-urlencode "password@$(sf "$pb")" --data-urlencode role=unit --data-urlencode "unit_id=$uid_b" >/dev/null
CSRF_PAGE=/admin post admin /admin/users --data-urlencode username=viewer-a --data-urlencode "password@$(sf "$pv")" --data-urlencode role=viewer --data-urlencode "unit_id=$uid_a" >/dev/null
check FR-APP-13 "sai mat khau bi tu choi" 200 "$(login unit-a sai-mat-khau | cut -d' ' -f1)"
check FR-APP-13 "unit-a dang nhap" "303 $P/" "$(login unit-a "$pa")"
check FR-APP-13 "unit-b dang nhap" "303 $P/" "$(login unit-b "$pb")"
check FR-APP-13 "viewer-a dang nhap" "303 $P/" "$(login viewer-a "$pv")"
check FR-APP-13 "unit-a khong vao /admin" 403 "$(get unit-a /admin)"

echo "== FR-APP-14 chien dich 3 link"
end=$(TZ=Asia/Ho_Chi_Minh date -d '+1 day' +%Y-%m-%dT%H:%M)
r=$(post unit-a /campaigns --data-urlencode "name=Smoke $rid" --data-urlencode "ends_at=$end" \
  --data-urlencode $'links=https://example.org/a1?r='"$rid"$' | Mot\nhttps://example.org/a2?r='"$rid"$' | Hai\nhttps://example.org/a3?r='"$rid"' | Ba')
cid=${r##*/campaigns/}
check FR-APP-14 "tao chien dich" 303 "${r%% *}"
get unit-a "/campaigns/$cid" >/dev/null
mapfile -t shorts < <(grep -oE 'http://localhost:18080/[A-Za-z0-9_-]+' "$work/out" | sort -u)
check FR-APP-14 "chien dich co 3 link" 3 "${#shorts[@]}"
ok=0; for s in "${shorts[@]}"; do [[ $(loc "${s/localhost/127.0.0.1}") == "302 https://example.org/a"* ]] && ok=$((ok+1)); done
check FR-APP-14 "3 link chuyen huong 302 toi dich" 3 "$ok"
tag="campaign-$cid"
hk_a=$(sf "X-Api-Key: $(cat "$sec/api_key_portal-donvi-a")")
hk_b=$(sf "X-Api-Key: $(cat "$sec/api_key_portal-donvi-b")")
check FR-APP-14 "3 link mang tag chien dich (REST key A)" 3 \
  "$(curl -sS -H @"$hk_a" "$S/rest/v3/short-urls?tags%5B%5D=$tag&itemsPerPage=50" | jq '.shortUrls.data | length')"

echo "== FR-APP-13 cach ly don vi"
check FR-APP-13 "unit-b xem chien dich cua A qua portal" 404 "$(get unit-b "/campaigns/$cid")"
check FR-APP-13 "unit-b khong thay chien dich A trong danh sach" 0 "$(get unit-b /campaigns >/dev/null; grep -c "Smoke $rid" "$work/out")"
code1=${shorts[0]##*/}
check FR-APP-13 "REST key B doc link cua A" 404 "$(curl -sS -o /dev/null -w '%{http_code}' -H @"$hk_b" "$S/rest/v3/short-urls/$code1")"
check FR-APP-13 "REST key B xem visit tag cua A" 0 "$(curl -sS -H @"$hk_b" "$S/rest/v3/short-urls?tags%5B%5D=$tag" | jq '.shortUrls.data | length')"
check FR-APP-13 "viewer-a xem chien dich cua A" 200 "$(get viewer-a "/campaigns/$cid")"
check FR-APP-13 "viewer-a khong tao duoc chien dich" 403 "$(CSRF_PAGE=/campaigns post viewer-a /campaigns --data-urlencode name=x --data-urlencode "ends_at=$end" | cut -d' ' -f1)"

echo "== FR-APP-16 phat hanh the (duong lui 1 lo)"
N=${CARDS_N:-10}
att=$(for i in $(seq 1 "$N"); do printf 'Người thử %02d, Đơn vị A\n' "$i"; done)
r=$(CSRF_PAGE="/campaigns/$cid" post unit-a "/campaigns/$cid/cards" --data-urlencode "target_url=https://example.org/checkin?r=$rid" --data-urlencode "attendees=$att")
check FR-APP-16 "phat hanh $N the" 303 "${r%% *}"
get unit-a "/campaigns/$cid" >/dev/null
pdf=$(grep -oE "/campaigns/$cid/cards/[0-9]+\.pdf" "$work/out" | head -1)
check FR-APP-16 "co link tai PDF" yes "$([[ -n $pdf ]] && echo yes || echo no)"
code=$(curl -sS -o "$work/the.pdf" -w '%{http_code}' -b "$(jar unit-a)" "$P$pdf")
check FR-APP-16 "tai PDF (unit-a)" "200 %PDF" "$code $(head -c4 "$work/the.pdf")"
check FR-APP-16 "PDF co $(( (N+7)/8 )) trang (8 the/trang)" "$(( (N+7)/8 ))" "$(python3 -c 'import re,sys; print(len(re.findall(rb"/Type\s*/Page(?![a-z])", open(sys.argv[1],"rb").read())))' "$work/the.pdf")"
check FR-APP-16 "unit-b tai PDF cua A" 404 "$(curl -sS -o /dev/null -w '%{http_code}' -b "$(jar unit-b)" "$P$pdf")"
mapfile -t cl < <(curl -sS -H @"$hk_a" "$S/rest/v3/short-urls?tags%5B%5D=$tag&itemsPerPage=100" \
  | jq -r --arg u "https://example.org/checkin?r=$rid" '.shortUrls.data[] | select(.longUrl == $u) | .shortCode')
check FR-APP-16 "$N nguoi ra $N link khac nhau" "$N" "$(printf '%s\n' "${cl[@]}" | sort -u | grep -c .)"
ok=0; for s in "${cl[@]}"; do [[ $(loc "$S/$s") == "302 https://example.org/checkin?r=$rid" ]] && ok=$((ok+1)); done
check FR-APP-16 "moi link the 302 dung dich" "$N" "$ok"
cp "$work/the.pdf" "$here/../../compose/secrets/the-qr-smoke.pdf" 2>/dev/null || true

echo "== FR-APP-14 sua han, dong chien dich"
r=$(CSRF_PAGE="/campaigns/$cid" post unit-a "/campaigns/$cid/edit" --data-urlencode "name=Smoke $rid (sua)" --data-urlencode "ends_at=$(TZ=Asia/Ho_Chi_Minh date -d '+2 day' +%Y-%m-%dT%H:%M)")
check FR-APP-14 "sua chien dich" 303 "${r%% *}"
check FR-APP-14 "link van 302 sau khi gia han" "302" "$(loc "${shorts[0]/localhost/127.0.0.1}" | cut -d' ' -f1)"
r=$(CSRF_PAGE="/campaigns/$cid" post unit-a "/campaigns/$cid/close")
check FR-APP-14 "dong chien dich" 303 "${r%% *}"
sleep 2
ok=0; for s in "${shorts[@]}"; do [[ $(loc "${s/localhost/127.0.0.1}" | cut -d' ' -f1) == 404 ]] && ok=$((ok+1)); done
check FR-APP-14 "3 link khong con chuyen huong sau khi dong" 3 "$ok"
check FR-APP-14 "link the khong con chuyen huong" 404 "$(loc "$S/${cl[0]}" | cut -d' ' -f1)"

echo "== FR-APP-14 het han theo gio"
end2=$(TZ=Asia/Ho_Chi_Minh date -d '+2 minute' +%Y-%m-%dT%H:%M)
r=$(post unit-a /campaigns --data-urlencode "name=Het han $rid" --data-urlencode "ends_at=$end2" --data-urlencode "links=https://example.org/hh?r=$rid | HH")
cid2=${r##*/campaigns/}
get unit-a "/campaigns/$cid2" >/dev/null
s2=$(grep -oE 'http://localhost:18080/[A-Za-z0-9_-]+' "$work/out" | head -1)
check FR-APP-14 "truoc han: 302" 302 "$(loc "${s2/localhost/127.0.0.1}" | cut -d' ' -f1)"
wait_s=$(( $(TZ=Asia/Ho_Chi_Minh date -d "$end2" +%s) - $(date +%s) + 3 ))
echo "INFO  cho het han ${wait_s}s"
sleep "$(( wait_s > 0 ? wait_s : 0 ))"
check FR-APP-14 "sau han: khong chuyen huong" 404 "$(loc "${s2/localhost/127.0.0.1}" | cut -d' ' -f1)"

echo "== ket qua: $fails FAIL"
exit $((fails > 0))
