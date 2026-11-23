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

echo "== FR-APP-17 luat chuyen huong theo thiet bi, ngon ngu, moc gio"
r=$(post unit-a /campaigns --data-urlencode "name=Luat $rid" --data-urlencode "ends_at=$end" --data-urlencode "links=https://example.org/mac-dinh?r=$rid | Mac dinh")
cid3=${r##*/campaigns/}
get unit-a "/campaigns/$cid3" >/dev/null
code3=$(grep -oE "/campaigns/$cid3/links/[A-Za-z0-9_-]+/rules" "$work/out" | head -1 | cut -d/ -f5)
rules="/campaigns/$cid3/links/$code3/rules"
UA_ANDROID='Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36'
UA_IOS='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
UA_PC='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
rloc() { curl -sS -o /dev/null -w '%{redirect_url}' -A "$1" ${2:+-H "Accept-Language: $2"} "$S/$code3"; }   # UA [ngon ngu] -> header Location
nrules() { get unit-a "$rules" >/dev/null; grep -c 'name="index"' "$work/out"; }
dest="https://example.org"
rule() { CSRF_PAGE="$rules" post "$@"; }   # unit-a/admin: lay CSRF tu chinh trang luat; in "code location"
check FR-APP-17 "trang luat cua unit-a" 200 "$(get unit-a "$rules")"
check FR-APP-17 "viewer-a khong xem trang luat" 403 "$(get viewer-a "$rules")"
check FR-APP-17 "viewer-a khong dat duoc luat" 403 "$(CSRF_PAGE=/campaigns post viewer-a "$rules" --data-urlencode kind=device --data-urlencode device=ios --data-urlencode "long_url=$dest/x" | cut -d' ' -f1)"
check FR-APP-17 "unit-b khong xem trang luat cua A" 404 "$(get unit-b "$rules")"
check FR-APP-17 "unit-b khong dat duoc luat cua A" 404 "$(CSRF_PAGE=/campaigns post unit-b "$rules" --data-urlencode kind=device --data-urlencode device=ios --data-urlencode "long_url=$dest/x" | cut -d' ' -f1)"
check FR-APP-17 "link chua co luat: Android ve dich mac dinh" "$dest/mac-dinh?r=$rid" "$(rloc "$UA_ANDROID")"

r=$(rule unit-a "$rules" --data-urlencode kind=device --data-urlencode device=android --data-urlencode "long_url=$dest/android?r=$rid")
check FR-APP-17 "dat luat Android" 303 "${r%% *}"
r=$(rule unit-a "$rules" --data-urlencode kind=device --data-urlencode device=ios --data-urlencode "long_url=$dest/ios?r=$rid")
check FR-APP-17 "dat luat iOS" 303 "${r%% *}"
check FR-APP-17 "User-Agent Android: Location rieng" "$dest/android?r=$rid" "$(rloc "$UA_ANDROID")"
check FR-APP-17 "User-Agent iOS: Location rieng" "$dest/ios?r=$rid" "$(rloc "$UA_IOS")"
check FR-APP-17 "Android va iOS ra 2 Location khac nhau" 2 "$(printf '%s\n%s\n' "$(rloc "$UA_ANDROID")" "$(rloc "$UA_IOS")" | sort -u | grep -c .)"
check FR-APP-17 "may tinh khong khop luat: ve dich mac dinh" "$dest/mac-dinh?r=$rid" "$(rloc "$UA_PC")"
r=$(rule admin "$rules" --data-urlencode kind=language --data-urlencode language=vi --data-urlencode "long_url=$dest/vi?r=$rid")
check FR-APP-17 "admin dat luat ngon ngu" 303 "${r%% *}"
check FR-APP-17 "Accept-Language vi: Location rieng" "$dest/vi?r=$rid" "$(rloc "$UA_PC" 'vi-VN,vi;q=0.9')"
check FR-APP-17 "Accept-Language en: ve dich mac dinh" "$dest/mac-dinh?r=$rid" "$(rloc "$UA_PC" en-US)"
check FR-APP-17 "co 3 luat tren trang" 3 "$(nrules)"

past=$(TZ=UTC-7 date -d '-1 day' +%Y-%m-%dT%H:%M); future=$(TZ=UTC-7 date -d '+30 day' +%Y-%m-%dT%H:%M)
r=$(rule unit-a "$rules" --data-urlencode kind=after-date --data-urlencode "when=$past" --data-urlencode position=1 --data-urlencode "long_url=$dest/sau-moc?r=$rid")
check FR-APP-17 "dat luat sau moc gio (da qua), uu tien 1" 303 "${r%% *}"
check FR-APP-17 "sau moc: Android ra dich thu ba" "$dest/sau-moc?r=$rid" "$(rloc "$UA_ANDROID")"
check FR-APP-17 "sau moc: iOS ra dich thu ba" "$dest/sau-moc?r=$rid" "$(rloc "$UA_IOS")"
r=$(rule unit-a "$rules" --data-urlencode kind=before-date --data-urlencode "when=$future" --data-urlencode position=1 --data-urlencode "long_url=$dest/truoc-moc?r=$rid")
check FR-APP-17 "dat luat truoc moc gio (tuong lai), uu tien 1" 303 "${r%% *}"
check FR-APP-17 "truoc moc: may tinh ra dich rieng" "$dest/truoc-moc?r=$rid" "$(rloc "$UA_PC")"

r=$(rule unit-a "$rules/delete" --data-urlencode index=1 --data-urlencode "expect=$dest/sau-moc?r=$rid")
check FR-APP-17 "xoa sai luat (danh sach da doi): khong xoa" 5 "$(nrules)"
r=$(rule unit-a "$rules/delete" --data-urlencode index=1 --data-urlencode "expect=$dest/truoc-moc?r=$rid")
r=$(rule unit-a "$rules/delete" --data-urlencode index=1 --data-urlencode "expect=$dest/sau-moc?r=$rid")
check FR-APP-17 "xoa 2 luat moc gio: con 3 luat" 3 "$(nrules)"
check FR-APP-17 "sau khi xoa luat: Android tro lai dich rieng" "$dest/android?r=$rid" "$(rloc "$UA_ANDROID")"

r=$(rule unit-a "$rules" --data-urlencode kind=device --data-urlencode device=toaster --data-urlencode "long_url=$dest/x")
check FR-APP-17 "thiet bi la: bi tu choi, khong them luat" 3 "$(nrules)"
r=$(rule unit-a "$rules" --data-urlencode kind=after-date --data-urlencode when= --data-urlencode "long_url=$dest/x")
check FR-APP-17 "thieu moc gio: bi tu choi, khong them luat" 3 "$(nrules)"
r=$(rule unit-a "$rules" --data-urlencode kind=language --data-urlencode language=khong-hop-le-qua-dai --data-urlencode "long_url=$dest/x")
check FR-APP-17 "ngon ngu sai dinh dang: bi tu choi" 3 "$(nrules)"
r=$(rule unit-a "$rules" --data-urlencode kind=device --data-urlencode device=ios --data-urlencode "long_url=javascript:alert(1)")
check FR-APP-17 "dich khong phai http(s): bi tu choi" 3 "$(nrules)"
check FR-APP-17 "thieu CSRF: 400" 400 "$(curl -sS -o /dev/null -w '%{http_code}' -b "$(jar unit-a)" "$P$rules" --data-urlencode kind=device --data-urlencode device=ios --data-urlencode "long_url=$dest/x")"
check FR-APP-17 "chien dich da dong: xem duoc trang luat" 200 "$(get unit-a "/campaigns/$cid/links/${shorts[0]##*/}/rules")"
check FR-APP-17 "chien dich da dong: khong dat them luat" 400 "$(CSRF_PAGE=/campaigns post unit-a "/campaigns/$cid/links/${shorts[0]##*/}/rules" --data-urlencode kind=device --data-urlencode device=ios --data-urlencode "long_url=$dest/x" | cut -d' ' -f1)"

echo "== FR-APP-15 nhap link tu CSV (dong bo)"
r=$(post unit-a /campaigns --data-urlencode "name=CSV $rid" --data-urlencode "ends_at=$end")
cid4=${r##*/campaigns/}
tag4="campaign-$cid4"
imp() { # ai, id chien dich, tep csv -> ma HTTP; noi dung tra ve o $work/out
  local t; t=$(csrf "$1" /campaigns)
  curl -sS -o "$work/out" -b "$(jar "$1")" -w '%{http_code}' "$P/campaigns/$2/import" --form-string "csrf=$t" -F "file=@$3;type=text/csv"
}
tong() { sed -n "s/.*data-$1=\"\([0-9]*\)\".*/\1/p" "$work/out" | head -1; }   # ok | exists | error trong trang ket qua
n_tag() { curl -sS -H @"$hk_a" "$S/rest/v3/short-urls?tags%5B%5D=$tag4&itemsPerPage=100" | jq '.shortUrls.data | length'; }
csv="$work/links.csv"
{
  echo 'long_url,custom_slug,label'
  for i in $(seq 1 16); do printf 'https://example.org/csv/%s/%02d,,Dong %02d\n' "$rid" "$i" "$i"; done
  printf 'https://example.org/csv/%s/17,csv-%s-17,"Co slug, dau phay"\n' "$rid" "$rid"
  printf 'https://example.org/csv/%s/18,csv-%s-18,Co slug\n' "$rid" "$rid"
  echo 'khong-phai-url,,URL sai'
  printf 'https://example.org/csv/%s/20,csv-%s-17,Trung slug\n' "$rid" "$rid"
} > "$csv"
check FR-APP-15 "file CSV co 20 dong du lieu (2 dong loi co y)" 20 "$(( $(wc -l < "$csv") - 1 ))"
check FR-APP-15 "unit-a nhap CSV" 200 "$(imp unit-a "$cid4" "$csv")"
check FR-APP-15 "18 link moi" 18 "$(tong ok)"
check FR-APP-15 "0 link da co" 0 "$(tong exists)"
check FR-APP-15 "2 dong loi" 2 "$(tong error)"
check FR-APP-15 "bao loi tung dong: URL sai" 1 "$(grep -c '<code>invalid-url</code>' "$work/out")"
check FR-APP-15 "bao loi tung dong: non-unique-slug" 1 "$(grep -c '<code>non-unique-slug</code>' "$work/out")"
check FR-APP-15 "Shlink co 18 link mang tag chien dich (REST key A)" 18 "$(n_tag)"
check FR-APP-15 "link CSV co slug: 302 toi dich" "302 https://example.org/csv/$rid/17" "$(loc "$S/csv-$rid-17" | cut -d' ' -f1,2)"
check FR-APP-15 "link CSV mang validUntil cua chien dich" 1 "$(curl -sS -H @"$hk_a" "$S/rest/v3/short-urls/csv-$rid-17" | grep -c '"validUntil":"20')"
get unit-a "/campaigns/$cid4" >/dev/null
check FR-APP-15 "trang chien dich liet ke 18 link" 18 "$(grep -oE 'http://localhost:18080/[A-Za-z0-9_-]+' "$work/out" | sort -u | wc -l)"
check FR-APP-15 "nhap lai cung file" 200 "$(imp unit-a "$cid4" "$csv")"
check FR-APP-15 "nhap lai: 0 link moi" 0 "$(tong ok)"
check FR-APP-15 "nhap lai: 18 link da co" 18 "$(tong exists)"
check FR-APP-15 "nhap lai: 2 dong loi van bao" 2 "$(tong error)"
check FR-APP-15 "nhap lai: Shlink van 18 link" 18 "$(n_tag)"

printf 'url,ghi_chu\nhttps://example.org/x,thieu cot long_url\n' > "$work/bad.csv"
check FR-APP-15 "file thieu cot long_url: bi tu choi" 303 "$(imp unit-a "$cid4" "$work/bad.csv")"
{ echo long_url; for i in $(seq 1 1001); do echo "https://example.org/qua-nhieu/$rid/$i"; done; } > "$work/big.csv"
check FR-APP-15 "file 1001 dong: bi tu choi" 303 "$(imp unit-a "$cid4" "$work/big.csv")"
check FR-APP-15 "file bi tu choi khong tao link" 18 "$(n_tag)"
check FR-APP-15 "viewer-a khong nhap duoc" 403 "$(imp viewer-a "$cid4" "$csv")"
check FR-APP-15 "unit-b nhap vao chien dich cua A" 404 "$(imp unit-b "$cid4" "$csv")"
check FR-APP-15 "chien dich da dong: khong nhap" 400 "$(imp unit-a "$cid" "$csv")"
check FR-APP-15 "thieu CSRF: 400" 400 "$(curl -sS -o /dev/null -w '%{http_code}' -b "$(jar unit-a)" "$P/campaigns/$cid4/import" -F "file=@$csv;type=text/csv")"
r=$(post unit-b /campaigns --data-urlencode "name=CSV B $rid" --data-urlencode "ends_at=$end")
printf 'long_url,custom_slug\nhttps://example.org/b/%s,csv-%s-17\n' "$rid" "$rid" > "$work/b.csv"
check FR-APP-15 "unit-b nhap slug da dung o don vi A" 200 "$(imp unit-b "${r##*/campaigns/}" "$work/b.csv")"
check FR-APP-15 "Shlink bao non-unique-slug cho dong do" 1 "$(grep -c '<code>non-unique-slug</code>' "$work/out")"

echo "== ket qua: $fails FAIL"
exit $((fails > 0))
