#!/bin/bash
# chaos-run.sh - FR-INF-24: chay campus_chaos.py THAT tren stack lab cua chaos-lab.sh (khong cham app VM cua nhom).
# Chay tren A (cung thu muc co chaos-lab.sh va campus_chaos.py):
#   sudo bash chaos-run.sh run     up lab -> thu rao an toan -> dry-run + 3 thi nghiem that + 1 thu dung som -> kiem Swift -> down (~20 phut)
#   sudo bash chaos-run.sh down    don neu bi ngat (hoan tac tu state, roi chaos-lab down)
# Quyen member (campus-tv2) nhu O-20; CHUA co credential rieng campus-chaos. Khong in token/secret.
# Nguong gia thuyet = ban sao scenarios/vm-stop.example.yaml da commit (15 s / 0 loi / 150 s), khong chinh sau khi xem ket qua.
set -u
umask 077
HERE=$(cd "$(dirname "$0")" && pwd)
cd /tmp
LAB=${LAB:-$HERE/chaos-lab.sh}
SRC=$HERE/campus_chaos.py
U=${LAB_USER:-tv2}
OWNER=${SUDO_USER:-root}
HOMEDIR=$(getent passwd "$OWNER" | cut -d: -f6)
OUT=${OUT:-$HOMEDIR/chaos-run-$(date -u +%Y%m%d).txt}
LABSTATE=$HOMEDIR/.chaos-lab.state
WD=/tmp/campus-chaos
HOLD=${HOLD:-45}
FMT=json
PASS=0; FAIL=0

say(){ echo "$*" | tee -a "$OUT"; }
ok(){ PASS=$((PASS+1)); say "PASS  $*"; }
bad(){ FAIL=$((FAIL+1)); say "FAIL  $*"; }
info(){ say "INFO  $*"; }
OSM(){ sudo -u "$U" -H env OS_CLOUD="campus-$U" openstack "$@"; }
CH(){ sudo -u "$U" -H env CHAOS_CLOUD="campus-$U" CHAOS_STATE_DIR="$WD" python3 "$WD/campus_chaos.py" "$@"; }
now(){ date +%s.%N; }
dur(){ awk -v a="$1" -v b="$2" 'BEGIN{printf "%.0f", b-a}'; }
indent(){ while read -r l; do info "  $l"; done; }

members_online(){ [ "$(OSM loadbalancer member list "$PO" -f value -c operating_status 2>/dev/null | grep -c '^ONLINE$')" = 2 ]; }
wait_online(){ local i; for i in $(seq 1 40); do members_online && return 0; sleep 3; done; return 1; }
load_lab(){ [ -s "$LABSTATE" ] || return 1; . "$LABSTATE"; [ -n "${FIP:-}" ] && [ -n "${PO:-}" ] && [ -n "${M1:-}" ] && [ -n "${M2:-}" ]; }

mk(){ # $1 ten  $2 hanh dong  $3 giu loi (s)  $4 online_members_lt  $5 ten VM dich
  NAME=$1 ACT=$2 HOLDS=$3 OML=$4 SRV=$5 POOLID=${PO:-x} PURL="http://${FIP:-x}:8080/" FMT=$FMT DEST="$WD/$1.$FMT" python3 - <<'PY'
import json, os
e = os.environ
sc = {
  'name': e['NAME'], 'action': e['ACT'], 'duration_s': int(e['HOLDS']), 'baseline_s': 10,
  'target': {'server': e['SRV'], 'pool': e['POOLID']},
  'probe': {'url': e['PURL'], 'rate_per_s': 4, 'timeout_s': 1, 'marker': 'chaos-lab-1'},
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

summ(){ # in tom tat tu file JSON ket qua cua campus_chaos: verdict, ly do dung som, checks, metrics
  python3 - "$1" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print('verdict=%s aborted=%s' % (d['verdict'], d.get('aborted_reason')))
print('checks=%s' % json.dumps(d['checks']))
print('metrics=%s' % json.dumps(d['metrics']))
print('report=%s' % d.get('report'))
PY
}

real(){ # $1 ten  $2 ky vong: PASS | ABORTED
  local n=$1 want=$2 f rc v reason
  f=$WD/$n.$FMT
  info "== chay that: $n (ky vong verdict $want) $(date -u +%H:%M:%SZ)"
  CH run "$f" > "$WD/out-$n.json" 2> "$WD/out-$n.err"; rc=$?
  info "rc=$rc"
  if [ -s "$WD/out-$n.err" ]; then info "stderr:"; head -c 600 "$WD/out-$n.err" | indent; fi
  if ! summ "$WD/out-$n.json" > "$WD/sum-$n.txt" 2>/dev/null; then bad "$n: khong doc duoc ket qua JSON (xem $WD/out-$n.json)"; head -c 600 "$WD/out-$n.json" | indent; return 1; fi
  indent < "$WD/sum-$n.txt"
  v=$(sed -n 's/^verdict=\([A-Z]*\) .*/\1/p' "$WD/sum-$n.txt")
  reason=$(sed -n 's/^verdict=[A-Z]* aborted=//p' "$WD/sum-$n.txt")
  if [ "$v" = "$want" ]; then ok "$n: verdict $v dung ky vong"; else bad "$n: verdict $v, ky vong $want"; fi
  if [ "$want" = ABORTED ]; then
    case "$reason" in *"member ONLINE"*) ok "$n: dung som vi $reason";; *) bad "$n: ly do dung som la '$reason', ky vong 'khong con member ONLINE'";; esac
  fi
  [ ! -e "$WD/state.json" ] && ok "$n: state.json da xoa (hoan tac xong)" || bad "$n: state.json con (hoan tac that bai? chay: sudo bash $0 down)"
  if wait_online; then ok "$n: ca hai member ONLINE sau thi nghiem"; else bad "$n: member chua ONLINE sau 2 phut"; fi
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
  local RES=$HOMEDIR/chaos-run-reports
  mkdir -p "$RES"
  cp "$WD"/reports/*.json "$RES"/ 2>/dev/null
  cp "$WD"/out-* "$WD"/sum-* "$WD"/*."$FMT" "$RES"/ 2>/dev/null
  chown -R "$OWNER" "$RES" 2>/dev/null
  info "ban sao ket qua o $RES: $(ls "$RES" | wc -l) file"
  [ -e "$WD/state.json" ] || rm -rf "$WD"
}

preflight(){
  [ -r "$LAB" ] || { bad "khong thay $LAB"; return 1; }
  [ -r "$SRC" ] || { bad "khong thay $SRC"; return 1; }
  info "may: $(hostname), $(date -u +%Y-%m-%dT%H:%M:%SZ), boot $(uptime -s)"
  info "python3: $(python3 --version 2>&1), openstack: $(OSM --version 2>&1 | head -1)"
  info "campus_chaos.py sha256: $(sha256sum "$SRC" | cut -d' ' -f1)"
  if [ -s "$LABSTATE" ]; then bad "con lab tu lan truoc ($LABSTATE): chay sudo bash $0 down"; return 1; fi
  if [ -e "$WD/state.json" ]; then bad "con $WD/state.json tu lan truoc: chay sudo bash $0 down"; return 1; fi
  if python3 -c 'import yaml' 2>/dev/null; then FMT=yaml; info "kich ban dung .yaml (PyYAML co): kiem duong doc .yaml"; else FMT=json; info "KHONG co PyYAML: kich ban dung .json (duong doc .yaml chua kiem)"; fi
  OSM server list >/dev/null 2>&1 || { bad "member $U khong goi duoc openstack (clouds.yaml campus-$U?)"; return 1; }
  rm -rf "$WD"; install -d -o "$U" -m 700 "$WD" || { bad "khong tao duoc $WD"; return 1; }
  install -m 644 -o "$U" "$SRC" "$WD/campus_chaos.py"
  ok "preflight: file, quyen member, thu muc lam viec $WD"
}

run(){
  local n t0 t1 objs
  t0=$(now)
  preflight || { down_all; return 1; }
  info "== 1. dung lab (chaos-lab.sh up)"
  bash "$LAB" up 2>&1 | grep -E '^(PASS|FAIL|INFO  ==)' | indent
  if ! load_lab; then bad "lab: khong co FIP/pool sau up"; down_all; collect; return 1; fi
  if wait_online && [ "$(for k in 1 2 3 4 5 6; do curl -s -m 2 "http://$FIP:8080/"; done | sort -u | wc -l)" = 2 ]; then ok "lab san sang: 2 member ONLINE, VIP tra loi tu 2 backend"; else bad "lab chua san sang"; down_all; collect; return 1; fi

  mk tat-vm-1 vm-stop "$HOLD" 1 chaos-lab-1
  mk tat-member-1 member-disable "$HOLD" 1 chaos-lab-1
  mk tat-port-1 port-disable "$HOLD" 1 chaos-lab-1
  mk dung-som-member-1 member-disable 30 3 chaos-lab-1
  mk tu-choi-campus-db vm-stop "$HOLD" 1 campus-db

  info "== 2. rao an toan: tu choi dich khong phai campus_role=app (chi doc, khong gay loi)"
  n=$(CH run "$WD/tu-choi-campus-db.$FMT" --dry-run 2>&1); local rc=$?
  echo "$n" | head -c 600 | indent
  if [ "$rc" = 2 ] && echo "$n" | grep -q 'TU CHOI'; then ok "campus-db bi tu choi truoc khi lam gi (rc=2)"
  else bad "rao an toan khong nhu ky vong (rc=$rc); neu thieu campus-db thi chua kiem duoc rao nay"; fi

  info "== 3. dry-run 3 hanh dong tren lab"
  for n in tat-vm-1 tat-member-1 tat-port-1; do
    CH run "$WD/$n.$FMT" --dry-run > "$WD/dry-$n.txt" 2>&1; rc=$?
    indent < "$WD/dry-$n.txt"
    [ "$rc" = 0 ] && ok "dry-run $n hop le" || bad "dry-run $n rc=$rc"
  done

  info "== 4. thi nghiem that (moi cai: nen 10 s, giu loi ${HOLD}s, hoan tac, doi hoi phuc)"
  for n in tat-vm-1 tat-member-1 tat-port-1; do real "$n" PASS; done
  info "== 5. thu dung som: online_members_lt=3 nen dung ngay sau khi gay loi (member-disable 30 s), phai hoan tac"
  real dung-som-member-1 ABORTED

  info "== 6. bao cao len Swift campus-reports/chaos/"
  objs=$(OSM object list campus-reports --prefix chaos/ -f value -c Name 2>&1)
  for n in tat-vm-1 tat-member-1 tat-port-1 dung-som-member-1; do
    if echo "$objs" | grep -q -- "-$n.json"; then ok "Swift co bao cao $n: $(echo "$objs" | grep -- "-$n.json" | tail -1)"; else bad "Swift khong co bao cao $n"; fi
  done
  n=$(echo "$objs" | grep -- '-tat-vm-1.json' | tail -1)
  if [ -n "$n" ] && OSM object save --file - campus-reports "$n" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print("doc lai tu Swift: verdict", d["verdict"])' > "$WD/swiftread.txt" 2>&1; then ok "doc lai bao cao tu Swift, JSON hop le"; indent < "$WD/swiftread.txt"; else bad "khong doc lai duoc bao cao tu Swift"; fi

  info "== 7. trang thai cuoi"
  CH status 2>&1 | indent
  CH status 2>&1 | grep -q 'khong co thi nghiem' && ok "status: khong co thi nghiem dang chay" || bad "status: con thi nghiem"

  info "== 8. don lab"
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
  say "== chaos-run ${1:-} bat dau $(date -u +%Y-%m-%dT%H:%M:%SZ) tren $(hostname)"
  case "${1:-}" in
    run) run;;
    down) down_all; collect;;
    *) echo "Dung: sudo bash $0 run | down"; exit 2;;
  esac
  say "== ket qua: $PASS PASS, $FAIL FAIL ($(date -u +%Y-%m-%dT%H:%M:%SZ)). File: $OUT"
}

main "$@"
