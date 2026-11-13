#!/bin/bash
# chaos-kill.sh - FR-INF-24, cot "Kiem bang" cua SRS 1.4: (1) kill tien trinh campus_chaos GIUA CHUNG roi `campus_chaos.py revert` hoan tac duoc;
# (2) mot lan chay vm-stop 120 s voi probe 30 req/s: bao cao co du so do va dich tro ve trang thai truoc loi.
# Chay tren A (cung thu muc co chaos-lab.sh va campus_chaos.py):
#   sudo bash chaos-kill.sh run     up lab -> kill giua chung (vm-stop, member-disable) + revert -> chay 120 s 30 req/s -> kiem Swift -> down (~10 phut)
#   sudo bash chaos-kill.sh down    don neu bi ngat (hoan tac tu state, roi chaos-lab down)
# Quyen member (campus-tv2) nhu O-20. Khong in token/secret. Lab o AZ-A (B khong bat); probe bang Python tu A, khong phai k6.
# Ghi chu 13/11: ban da chay (sha256 76edbaa8...01aef) co loi o ham summ (doc khoa scenario khong co trong JSON in ra) lam in FAIL gia
# "khong doc duoc ket qua JSON" o buoc 3 va bo qua 2 kiem tra cuoi buoc do. Ban nay da sua 2 dong, CHUA chay lai.
set -u
umask 077
HERE=$(cd "$(dirname "$0")" && pwd)
cd /tmp
LAB=${LAB:-$HERE/chaos-lab.sh}
SRC=$HERE/campus_chaos.py
U=${LAB_USER:-tv2}
OWNER=${SUDO_USER:-root}
HOMEDIR=$(getent passwd "$OWNER" | cut -d: -f6)
OUT=${OUT:-$HOMEDIR/chaos-kill-$(date -u +%Y%m%d).txt}
LABSTATE=$HOMEDIR/.chaos-lab.state
WD=/tmp/campus-chaos
FMT=json
PASS=0; FAIL=0

say(){ echo "$*" | tee -a "$OUT"; }
ok(){ PASS=$((PASS+1)); say "PASS  $*"; }
bad(){ FAIL=$((FAIL+1)); say "FAIL  $*"; }
info(){ say "INFO  $*"; }
OSM(){ sudo -u "$U" -H env OS_CLOUD="campus-$U" openstack "$@"; }
CH(){ sudo -u "$U" -H env CHAOS_CLOUD="campus-$U" CHAOS_STATE_DIR="$WD" python3 "$WD/campus_chaos.py" "$@"; }
now(){ date +%s.%N; }
dur(){ awk -v a="$1" -v b="$2" 'BEGIN{printf "%.1f", b-a}'; }
indent(){ while read -r l; do info "  $l"; done; }

members_online(){ [ "$(OSM loadbalancer member list "$PO" -f value -c operating_status 2>/dev/null | grep -c '^ONLINE$')" = 2 ]; }
wait_online(){ local i; for i in $(seq 1 40); do members_online && return 0; sleep 3; done; return 1; }
load_lab(){ [ -s "$LABSTATE" ] || return 1; . "$LABSTATE"; [ -n "${FIP:-}" ] && [ -n "${PO:-}" ] && [ -n "${M1:-}" ] && [ -n "${M2:-}" ]; }
target_answers(){ for k in 1 2 3 4 5 6 7 8 9 10 11 12; do curl -s -m 2 "http://$FIP:8080/"; done | grep -q 'chaos-lab-1'; }

mk(){ # $1 ten  $2 hanh dong  $3 giu loi (s)  $4 online_members_lt  $5 ten VM dich  $6 probe/s  $7 nen (s)
  NAME=$1 ACT=$2 HOLDS=$3 OML=$4 SRV=$5 RATE=$6 BASES=$7 POOLID=${PO:-x} PURL="http://${FIP:-x}:8080/" FMT=$FMT DEST="$WD/$1.$FMT" python3 - <<'PY'
import json, os
e = os.environ
sc = {
  'name': e['NAME'], 'action': e['ACT'], 'duration_s': int(e['HOLDS']), 'baseline_s': int(e['BASES']),
  'target': {'server': e['SRV'], 'pool': e['POOLID']},
  'probe': {'url': e['PURL'], 'rate_per_s': int(e['RATE']), 'timeout_s': 1, 'marker': 'chaos-lab-1'},
  'stop_if': {'error_rate_gt': 0.2, 'window_s': 5, 'min_probes': 8, 'online_members_lt': int(e['OML'])},
  'hypothesis': {'detect_within_s': 15, 'max_errors_after_detect': 0, 'recover_within_s': 150},
  'report': {'swift_container': 'campus-reports'},
}
if e['FMT'] == 'yaml':
    import yaml
    txt = yaml.safe_dump(sc, sort_keys=False)
else:
    txt = json.dumps(sc, indent=2)
open(e['DEST'], 'w').write(txt)
PY
  chown "$U" "$WD/$1.$FMT"; chmod 644 "$WD/$1.$FMT"
}

fault_active(){ # $1=hanh dong: loi dang co hieu luc that tren lab?
  local st
  case "$1" in
    vm-stop) st=$(OSM server show chaos-lab-1 -f value -c status 2>/dev/null); [ "$st" = SHUTOFF ];;
    member-disable) st=$(OSM loadbalancer member show "$PO" "$M1" -f value -c admin_state_up 2>/dev/null | tr 'A-Z' 'a-z'); [ "$st" = false ];;
    *) return 1;;
  esac
}

kill_test(){ # $1=ten  $2=hanh dong
  local n=$1 act=$2 i active=0 t0 rec rc
  mk "$n" "$act" 120 1 chaos-lab-1 4 5
  info "== kill giua chung: $n ($act, giu loi 120 s; se kill -9 ngay khi loi co hieu luc) $(date -u +%H:%M:%SZ)"
  CH run "$WD/$n.$FMT" > "$WD/out-$n.json" 2> "$WD/out-$n.err" &
  for i in $(seq 1 45); do
    if [ -e "$WD/state.json" ] && fault_active "$act"; then active=1; break; fi
    sleep 2
  done
  if [ "$active" = 1 ]; then ok "$n: loi da co hieu luc that ($act) va state.json da ghi"; else bad "$n: khong thay loi co hieu luc sau 90 s"; fi
  pkill -9 -f "$WD/campus_chaos.py run"
  sleep 1
  wait 2>/dev/null
  if pgrep -f "$WD/campus_chaos.py run" >/dev/null; then bad "$n: tien trinh con song sau kill -9"; else ok "$n: tien trinh campus_chaos da bi kill -9 giua chung"; fi
  if [ -e "$WD/state.json" ]; then ok "$n: state.json con lai sau kill (de revert biet hoan tac gi)"; else bad "$n: state.json mat sau kill"; fi
  if fault_active "$act"; then ok "$n: loi van con hieu luc sau kill (khong ai hoan tac, dung ky vong)"; else info "$n: loi khong con hieu luc sau kill (bat thuong)"; fi
  CH status 2>&1 | head -c 700 | indent
  t0=$(now)
  CH revert > "$WD/revert-$n.txt" 2>&1; rc=$?
  indent < "$WD/revert-$n.txt"
  if [ "$rc" = 0 ]; then ok "$n: campus_chaos.py revert rc=0"; else bad "$n: campus_chaos.py revert rc=$rc"; fi
  rec=""
  for i in $(seq 1 60); do
    if members_online && target_answers; then rec=$(dur "$t0" "$(now)"); break; fi
    sleep 3
  done
  if [ -n "$rec" ]; then ok "$n: sau revert, 2 member ONLINE va chaos-lab-1 tra loi lai sau ${rec} s tinh tu luc go revert"; else bad "$n: sau revert chua hoi phuc trong 180 s"; fi
  if [ ! -e "$WD/state.json" ]; then ok "$n: state.json da xoa sau revert"; else bad "$n: state.json con sau revert"; fi
}

summ(){
  python3 - "$1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print('verdict=%s aborted=%s' % (d['verdict'], d.get('aborted_reason')))
print('checks=%s' % json.dumps(d['checks']))
print('metrics=%s' % json.dumps(d['metrics']))
print('probes_in_fault=%s' % d['metrics']['probes_in_fault'])
print('report=%s' % d.get('report'))
PY
}

long_run(){ # vm-stop 120 s, probe 30 req/s
  local n=tat-vm-120s-30rps v pf
  mk "$n" vm-stop 120 1 chaos-lab-1 30 10
  info "== chay that $n: vm-stop giu loi 120 s, probe 30 req/s (nen 10 s) $(date -u +%H:%M:%SZ)"
  CH run "$WD/$n.$FMT" > "$WD/out-$n.json" 2> "$WD/out-$n.err"; local rc=$?
  info "rc=$rc"
  if [ -s "$WD/out-$n.err" ]; then info "stderr:"; head -c 600 "$WD/out-$n.err" | indent; fi
  if ! summ "$WD/out-$n.json" > "$WD/sum-$n.txt" 2>/dev/null; then bad "$n: khong doc duoc ket qua JSON"; head -c 600 "$WD/out-$n.json" | indent; return 1; fi
  indent < "$WD/sum-$n.txt"
  v=$(sed -n 's/^verdict=\([A-Z]*\) .*/\1/p' "$WD/sum-$n.txt")
  if [ "$v" = PASS ]; then ok "$n: verdict PASS (gia thuyet khai truoc: phat hien <= 15 s, 0 loi sau phat hien, hoi phuc <= 150 s)"; else bad "$n: verdict $v"; fi
  pf=$(sed -n 's/^probes_in_fault=//p' "$WD/sum-$n.txt")
  info "probe thuc te trong luc loi: ${pf:-?} / 120 s = khoang $(awk -v p="${pf:-0}" 'BEGIN{printf "%.1f", p/120}') req/s (muc tieu 30)"
  [ ! -e "$WD/state.json" ] && ok "$n: state.json da xoa" || bad "$n: state.json con"
  if wait_online && target_answers; then ok "$n: dich tro ve trang thai truoc loi (2 member ONLINE, chaos-lab-1 tra loi)"; else bad "$n: dich chua tro ve trang thai truoc loi"; fi
}

down_all(){
  if [ -e "$WD/state.json" ]; then info "con state.json: hoan tac"; CH revert 2>&1 | indent; fi
  bash "$LAB" down 2>&1 | indent
  local left
  left=$(OSM server list -f value -c Name 2>/dev/null | grep -c '^chaos-lab-')
  left=$((left + $(OSM loadbalancer list -f value -c name 2>/dev/null | grep -c '^chaos-lab-')))
  if [ "$left" = 0 ] && [ ! -e "$LABSTATE" ]; then ok "down: khong con tai nguyen chaos-lab"; else bad "down: con $left tai nguyen hoac con $LABSTATE (chay lai: sudo bash $0 down)"; fi
}

collect(){
  local RES=$HOMEDIR/chaos-kill-reports
  mkdir -p "$RES"
  cp "$WD"/reports/*.json "$RES"/ 2>/dev/null
  cp "$WD"/out-* "$WD"/sum-* "$WD"/revert-* "$WD"/*."$FMT" "$RES"/ 2>/dev/null
  chown -R "$OWNER" "$RES" 2>/dev/null
  info "ban sao ket qua o $RES: $(ls "$RES" | wc -l) file"
  [ -e "$WD/state.json" ] || rm -rf "$WD"
}

preflight(){
  [ -r "$LAB" ] || { bad "khong thay $LAB"; return 1; }
  [ -r "$SRC" ] || { bad "khong thay $SRC"; return 1; }
  info "may: $(hostname), $(date -u +%Y-%m-%dT%H:%M:%SZ), boot $(uptime -s)"
  info "campus_chaos.py sha256: $(sha256sum "$SRC" | cut -d' ' -f1)"
  if [ -s "$LABSTATE" ]; then bad "con lab tu lan truoc ($LABSTATE): chay sudo bash $0 down"; return 1; fi
  if [ -e "$WD/state.json" ]; then bad "con $WD/state.json tu lan truoc: chay sudo bash $0 down"; return 1; fi
  if python3 -c 'import yaml' 2>/dev/null; then FMT=yaml; else FMT=json; fi
  info "dinh dang kich ban: $FMT"
  OSM server list >/dev/null 2>&1 || { bad "member $U khong goi duoc openstack"; return 1; }
  rm -rf "$WD"; install -d -o "$U" -m 700 "$WD" || { bad "khong tao duoc $WD"; return 1; }
  install -m 644 -o "$U" "$SRC" "$WD/campus_chaos.py"
  ok "preflight: file, quyen member, thu muc lam viec $WD"
}

run(){
  local t0 t1 objs n
  t0=$(now)
  preflight || { down_all; return 1; }
  info "== 1. dung lab (chaos-lab.sh up)"
  bash "$LAB" up 2>&1 | grep -E '^(PASS|FAIL|INFO  ==)' | indent
  if ! load_lab; then bad "lab: khong co FIP/pool sau up"; down_all; collect; return 1; fi
  if wait_online && target_answers; then ok "lab san sang: 2 member ONLINE, VIP tra loi"; else bad "lab chua san sang"; down_all; collect; return 1; fi

  info "== 2. kill -9 giua chung roi revert (hanh dong vm-stop, roi member-disable)"
  kill_test kill-vm-1 vm-stop
  kill_test kill-member-1 member-disable

  info "== 3. chay that 120 s voi probe 30 req/s"
  long_run

  info "== 4. bao cao tren Swift campus-reports/chaos/ (chi lan chay 120 s co bao cao; hai lan bi kill khong co, dung ky vong)"
  objs=$(OSM object list campus-reports --prefix chaos/ -f value -c Name 2>&1)
  if echo "$objs" | grep -q -- '-tat-vm-120s-30rps.json'; then ok "Swift co bao cao tat-vm-120s-30rps: $(echo "$objs" | grep -- '-tat-vm-120s-30rps.json' | tail -1)"; else bad "Swift khong co bao cao tat-vm-120s-30rps"; fi

  info "== 5. trang thai cuoi"
  CH status 2>&1 | indent
  CH status 2>&1 | grep -q 'khong co thi nghiem' && ok "status: khong co thi nghiem dang chay" || bad "status: con thi nghiem"

  info "== 6. don lab"
  down_all
  collect
  t1=$(now)
  info "tong thoi gian $(dur "$t0" "$t1") s"
}

abort(){ echo; say "NGAT: hoan tac va don lab"; down_all; collect; exit 130; }
on_exit(){ chown "$OWNER" "$OUT" 2>/dev/null; }

main(){
  if [ "$(id -u)" != 0 ]; then echo "Chay bang: sudo bash $0 <run|down>"; exit 2; fi
  trap on_exit EXIT
  trap abort INT TERM
  say "== chaos-kill ${1:-} bat dau $(date -u +%Y-%m-%dT%H:%M:%SZ) tren $(hostname)"
  case "${1:-}" in
    run) run;;
    down) down_all; collect;;
    *) echo "Dung: sudo bash $0 run | down"; exit 2;;
  esac
  say "== ket qua: $PASS PASS, $FAIL FAIL ($(date -u +%Y-%m-%dT%H:%M:%SZ)). File: $OUT"
}

main "$@"
