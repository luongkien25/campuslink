#!/bin/bash
# chaos-lab.sh - FR-INF-24 giai doan 1, SRS O-20: stack lab 2 VM (campus_role=app) sau LB ovn,
# thu 3 hanh dong loi bang quyen member (campus-tv2), do phat hien/hoi phuc va loi nhin thay.
# Chay tren A:  sudo bash chaos-lab.sh run        (up + 3 thi nghiem + down, khoang 10 phut)
#               sudo bash chaos-lab.sh up | exp <vm-stop|member-disable|port-disable> | status | down
# Khong dung admin cho thao tac loi. Tai nguyen deu ten chaos-lab-*. Khong in token/secret.
set -u
umask 077
U=${LAB_USER:-tv2}
OWNER=${SUDO_USER:-root}
HOMEDIR=$(getent passwd "$OWNER" | cut -d: -f6)
STATE=$HOMEDIR/.chaos-lab.state
OUT=${OUT:-$HOMEDIR/chaos-lab-$(date -u +%Y%m%d).txt}
NET=campus-net
SUBNET=59399337-e22b-4237-87dd-bf4ac035bcfa
FLAVOR=campus.app
IMAGE=ubuntu-noble-base
SG=campus-app-sg
AZ=${LAB_AZ:-campus-az-a}
HOLD=${HOLD:-45}
BASE=${BASE:-10}
RECOVER_MAX=${RECOVER_MAX:-150}
TS=${TIMESCALE:-1}
PASS=0; FAIL=0

say(){ echo "$*" | tee -a "$OUT"; }
ok(){ PASS=$((PASS+1)); say "PASS  $*"; }
bad(){ FAIL=$((FAIL+1)); say "FAIL  $*"; }
info(){ say "INFO  $*"; }
OSM(){ sudo -u "$U" -H env OS_CLOUD="campus-$U" openstack "$@"; }
nap(){ sleep "$(awk -v s="$1" -v f="$TS" 'BEGIN{print s*f}')"; }
now(){ date +%s.%N; }
st_set(){ echo "$1=$2" >> "$STATE"; }
load_state(){ [ -s "$STATE" ] || { bad "chua co lab (chay: up)"; return 1; }; . "$STATE"; }
pick(){ awk -v n="$1" '{f=0;s="";for(i=1;i<=NF;i++){if($i==n)f=1;else s=$i} if(f){print s;exit}}'; }
mlist(){ OSM loadbalancer member list "$PO" -f value -c name -c operating_status 2>/dev/null; }

lbwait(){ # doi LB ACTIVE (toi da 120 s)
  local i s
  for i in $(seq 1 60); do
    s=$(OSM loadbalancer show "$LB" -f value -c provisioning_status 2>/dev/null)
    [ "$s" = ACTIVE ] && return 0
    [ "$s" = ERROR ] && return 1
    nap 2
  done
  return 1
}

web_ready(){ # ca hai backend tra loi qua VIP (toi da ~3 phut)
  local i seen
  for i in $(seq 1 60); do
    seen=$(for k in 1 2 3 4 5 6 7 8 9 10 11 12; do curl -s -m 2 "http://$FIP:8080/"; done | sort -u | tr '\n' ' ')
    case "$seen" in *chaos-lab-1*chaos-lab-2*) return 0;; esac
    nap 3
  done
  return 1
}

up(){
  local W n id ip pt
  if [ -s "$STATE" ]; then bad "up: da co $STATE (chay: down truoc)"; return 1; fi
  info "== up: dung lab 2 VM + LB ovn"
  info "han muc (member $U):"
  OSM limits show --absolute 2>/dev/null | grep -i -E 'instance|core|ram|floating' | while read -r l; do info "  $l"; done
  W=$(mktemp -d); chmod 755 "$W"
  cat > "$W/ud.yaml" <<'EOF'
#cloud-config
write_files:
  - path: /etc/systemd/system/chaos-web.service
    content: |
      [Unit]
      Description=chaos lab web
      After=network-online.target
      [Service]
      ExecStart=/usr/bin/python3 -m http.server 8080 --directory /srv/chaos-web
      Restart=always
      [Install]
      WantedBy=multi-user.target
runcmd:
  - mkdir -p /srv/chaos-web
  - hostname > /srv/chaos-web/index.html
  - systemctl daemon-reload
  - systemctl enable --now chaos-web.service
EOF
  chmod 644 "$W/ud.yaml"
  : > "$STATE"; chmod 600 "$STATE"
  for n in 1 2; do
    id=$(OSM server create --flavor "$FLAVOR" --image "$IMAGE" --network "$NET" --security-group "$SG" \
         --availability-zone "$AZ" --user-data "$W/ud.yaml" --property campus_role=app --wait \
         -f value -c id "chaos-lab-$n" 2>"$W/s$n.err")
    if [ -z "$id" ]; then bad "up: tao chaos-lab-$n loi: $(head -c 300 "$W/s$n.err" | tr '\n' ' ')"; rm -rf "$W"; return 1; fi
    st_set VM$n "$id"
    ip=$(OSM server show "$id" -f value -c addresses | grep -oE '10\.20\.0\.[0-9]+' | head -1)
    pt=$(OSM port list --server "$id" -f value -c ID | head -1)
    st_set IP$n "$ip"; st_set PT$n "$pt"
    ok "up: chaos-lab-$n ACTIVE (campus_role=app, $AZ) ip=$ip"
  done
  rm -rf "$W"
  load_state
  LB=$(OSM loadbalancer create --name chaos-lab-lb --vip-subnet-id "$SUBNET" --provider ovn -f value -c id)
  [ -n "$LB" ] || { bad "up: tao LB loi"; return 1; }
  st_set LB "$LB"
  lbwait || { bad "up: LB khong ACTIVE"; return 1; }
  st_set VIP "$(OSM loadbalancer show "$LB" -f value -c vip_address)"
  st_set VIPPORT "$(OSM loadbalancer show "$LB" -f value -c vip_port_id)"
  load_state
  LI=$(OSM loadbalancer listener create --name chaos-lab-l --protocol TCP --protocol-port 8080 -f value -c id "$LB"); st_set LI "$LI"; lbwait || { bad "up: listener loi"; return 1; }
  PO=$(OSM loadbalancer pool create --name chaos-lab-p --lb-algorithm SOURCE_IP_PORT --listener "$LI" --protocol TCP -f value -c id); st_set PO "$PO"; lbwait || { bad "up: pool loi"; return 1; }
  HM=$(OSM loadbalancer healthmonitor create --name chaos-lab-hm --delay 5 --timeout 3 --max-retries 2 --type TCP -f value -c id "$PO"); st_set HM "$HM"; lbwait || { bad "up: health monitor loi"; return 1; }
  M1=$(OSM loadbalancer member create --name m1 --address "$IP1" --protocol-port 8080 --subnet-id "$SUBNET" -f value -c id "$PO"); st_set M1 "$M1"; lbwait || { bad "up: member m1 loi"; return 1; }
  M2=$(OSM loadbalancer member create --name m2 --address "$IP2" --protocol-port 8080 --subnet-id "$SUBNET" -f value -c id "$PO"); st_set M2 "$M2"; lbwait || { bad "up: member m2 loi"; return 1; }
  FIP=$(OSM floating ip create public --port "$VIPPORT" -f value -c floating_ip_address)
  [ -n "$FIP" ] || { bad "up: tao FIP cho VIP loi"; return 1; }
  st_set FIP "$FIP"
  ok "up: LB ovn ACTIVE, VIP=$VIP, FIP=$FIP, pool SOURCE_IP_PORT, HM TCP 5/3/2, 2 member"
  load_state
  if web_ready; then ok "up: ca hai backend tra loi qua VIP (chaos-lab-1, chaos-lab-2)"; else bad "up: backend chua tra loi sau ~3 phut (doc console log: openstack console log show chaos-lab-1)"; return 1; fi
  if [ "$(mlist | pick m1)" = ONLINE ] && [ "$(mlist | pick m2)" = ONLINE ]; then ok "up: m1, m2 ONLINE"; else bad "up: member chua ca hai ONLINE: $(mlist | tr '\n' ' ')"; return 1; fi
}

do_fault(){
  case "$1" in
    vm-stop) OSM server stop "$VM1";;
    member-disable) OSM loadbalancer member set --disable "$PO" "$M1";;
    port-disable) OSM port set --disable "$PT1";;
  esac
}
do_revert(){
  case "$1" in
    vm-stop) OSM server start "$VM1";;
    member-disable) OSM loadbalancer member set --enable "$PO" "$M1";;
    port-disable) OSM port set --enable "$PT1";;
  esac
}

# phan tich: doc probe.log (epoch ma-http than), status.log (epoch trang-thai-m1 trang-thai-m2)
# in: td (giay tu loi toi khi m1 khong con ONLINE), tr (giay tu hoan tac toi khi m1 ONLINE lai), n err ... ; tham so: dir t0 t1 target
analyze(){
  local d=$1 t0=$2 t1=$3 tg=$4 td tr
  td=$(awk -v t0="$t0" '$1>t0 && $2!="ONLINE" && $2!="?" {printf "%.1f", $1-t0; exit}' "$d/status.log")
  tr=$(awk -v t1="$t1" '$1>t1 && $2=="ONLINE" {printf "%.1f", $1-t1; exit}' "$d/status.log")
  echo "td=${td:--} tr=${tr:--}"
  awk -v t0="$t0" -v t1="$t1" -v td="${td:-}" -v tg="$tg" '
    $1>=t0 && $1<=t1 { n++
      if ($2!="200") { e++; if (td!="" && $1>=t0+td+2) ea++ }
      if ($3==tg) { r++; if (td!="" && $1>=t0+td+2) ra++ } }
    $1>t1 && $3==tg && fr=="" { fr=sprintf("%.1f", $1-t1) }
    END { printf "n=%d err=%d err_sau_phat_hien=%d resp_target=%d resp_target_sau_phat_hien=%d target_tra_loi_lai=%s\n", n, e, ea, r, ra, (fr==""?"-":fr) }
  ' "$d/probe.log"
}

recovered(){ # m1 ONLINE sau t1 va probe thay target tra loi lai
  local d=$1 t1=$2 tg=$3
  awk -v t1="$t1" '$1>t1 && $2=="ONLINE" {f=1} END{exit f?0:1}' "$d/status.log" || return 1
  awk -v t1="$t1" -v tg="$tg" '$1>t1 && $3==tg {f=1} END{exit f?0:1}' "$d/probe.log"
}

exp(){
  local name=${1:-} W t0 t1 frc rrc ppid spid i res a b tg=chaos-lab-1 td tr
  case "$name" in vm-stop|member-disable|port-disable) ;; *) echo "thi nghiem: vm-stop | member-disable | port-disable"; return 2;; esac
  load_state || return 1
  info "== thi nghiem $name: nen ${BASE}s, giu loi ${HOLD}s, hoi phuc toi da ${RECOVER_MAX}s; muc tieu m1 (chaos-lab-1)"
  if [ "$(mlist | pick m1)" = ONLINE ] && [ "$(mlist | pick m2)" = ONLINE ]; then :; else bad "$name: member chua ca hai ONLINE: $(mlist | tr '\n' ' ')"; return 1; fi
  W=$(mktemp -d); : > "$W/probe.log"; : > "$W/status.log"
  ( while :; do rm -f "$W/b"; c=$(curl -s -m 1 -o "$W/b" -w '%{http_code}' "http://$FIP:8080/"); echo "$(now) $c $(cat "$W/b" 2>/dev/null)"; nap 0.25; done >> "$W/probe.log" ) &
  ppid=$!
  ( while :; do l=$(mlist); a=$(echo "$l" | pick m1); b=$(echo "$l" | pick m2); echo "$(now) ${a:-?} ${b:-?}"; done >> "$W/status.log" ) &
  spid=$!
  nap "$BASE"
  t0=$(now)
  do_fault "$name" > "$W/f.out" 2>&1; frc=$?
  info "loi $name: rc=$frc $(head -c 200 "$W/f.out" | tr '\n' ' ')"
  nap "$HOLD"
  t1=$(now)
  do_revert "$name" > "$W/r.out" 2>&1; rrc=$?
  info "hoan tac $name: rc=$rrc $(head -c 200 "$W/r.out" | tr '\n' ' ')"
  i=0
  while [ "$i" -lt "$RECOVER_MAX" ]; do
    recovered "$W" "$t1" "$tg" && break
    nap 3; i=$((i+3))
  done
  nap 3
  kill "$ppid" "$spid" 2>/dev/null; wait "$ppid" "$spid" 2>/dev/null
  res=$(analyze "$W" "$t0" "$t1" "$tg")
  info "do $name: $(echo "$res" | tr '\n' ' ')"
  td=$(echo "$res" | sed -n 's/.*td=\([^ ]*\).*/\1/p' | head -1)
  tr=$(echo "$res" | sed -n 's/.*tr=\([^ ]*\).*/\1/p' | head -1)
  [ "$frc" = 0 ] && ok "$name: lenh gay loi duoc chap nhan (rc=0)" || bad "$name: lenh gay loi loi rc=$frc: $(head -c 200 "$W/f.out" | tr '\n' ' ')"
  [ "$rrc" = 0 ] && ok "$name: hoan tac duoc chap nhan (rc=0)" || bad "$name: hoan tac loi rc=$rrc: $(head -c 200 "$W/r.out" | tr '\n' ' ')"
  if [ "${td:--}" != "-" ]; then ok "$name: LB phat hien member khong ONLINE sau ${td}s"; else bad "$name: LB khong danh dau m1 khac ONLINE trong luc loi"; fi
  echo "$res" | grep -q 'err_sau_phat_hien=0 resp_target=[0-9]* resp_target_sau_phat_hien=0' && ok "$name: sau khi phat hien: 0 loi, 0 phan hoi tu muc tieu" || bad "$name: sau khi phat hien con loi hoac con phan hoi tu muc tieu (xem dong do)"
  if [ "${tr:--}" != "-" ] && ! echo "$res" | grep -q 'target_tra_loi_lai=-'; then ok "$name: hoi phuc: m1 ONLINE sau ${tr}s, muc tieu tra loi lai"; else bad "$name: khong hoi phuc trong ${RECOVER_MAX}s"; fi
  cp "$W/probe.log" "$HOMEDIR/chaos-lab-$name-probe.log" 2>/dev/null; cp "$W/status.log" "$HOMEDIR/chaos-lab-$name-status.log" 2>/dev/null
  rm -rf "$W"
}

status(){
  load_state || return 1
  info "VM:"; OSM server list --name chaos-lab -c Name -c Status -c Networks 2>/dev/null | while read -r l; do info "  $l"; done
  info "LB:"; OSM loadbalancer show "$LB" -c provisioning_status -c operating_status -c vip_address 2>/dev/null | while read -r l; do info "  $l"; done
  info "member: $(mlist | tr '\n' ' ')"
}

down(){
  local id left=0
  [ -s "$STATE" ] && . "$STATE"
  info "== down: don lab"
  [ -n "${FIP:-}" ] && OSM floating ip delete "$FIP" >/dev/null 2>&1
  if [ -n "${LB:-}" ]; then
    OSM loadbalancer delete --cascade "$LB" >/dev/null 2>&1
    for id in $(seq 1 45); do OSM loadbalancer show "$LB" >/dev/null 2>&1 || break; nap 2; done
  fi
  for id in $(OSM loadbalancer list -f value -c id -c name 2>/dev/null | awk '$2=="chaos-lab-lb"{print $1}'); do
    OSM loadbalancer delete --cascade "$id" >/dev/null 2>&1; nap 6
  done
  for id in $(OSM server list -f value -c ID -c Name 2>/dev/null | awk '$2 ~ /^chaos-lab-/ {print $1}'); do
    OSM server delete --wait "$id" >/dev/null 2>&1
  done
  left=$(OSM server list -f value -c Name 2>/dev/null | grep -c '^chaos-lab-')
  left=$((left + $(OSM loadbalancer list -f value -c name 2>/dev/null | grep -c '^chaos-lab-')))
  if [ -n "${FIP:-}" ] && OSM floating ip list -f value -c "Floating IP Address" 2>/dev/null | grep -q -x "$FIP"; then left=$((left+1)); fi
  if [ "$left" = 0 ]; then ok "down: khong con tai nguyen chaos-lab"; rm -f "$STATE"; else bad "down: con $left tai nguyen chaos-lab (server/LB/FIP); chay lai: sudo bash $0 down"; fi
}

run(){
  local e
  up && for e in vm-stop member-disable port-disable; do exp "$e"; done
  down
}

on_exit(){ kill $(jobs -p) 2>/dev/null; chown "$OWNER" "$OUT" "$HOMEDIR"/chaos-lab-*.log 2>/dev/null; }

main(){
  if [ "$(id -u)" != 0 ]; then echo "Chay bang: sudo bash $0 <run|up|exp|status|down>"; exit 2; fi
  trap on_exit EXIT
  say "== chaos-lab ${1:-} bat dau $(date -u +%Y-%m-%dT%H:%M:%SZ) tren $(hostname)"
  case "${1:-}" in
    run) run;;
    up) up;;
    exp) exp "${2:-}";;
    status) status;;
    down) down;;
    *) echo "Dung: sudo bash $0 run | up | exp <vm-stop|member-disable|port-disable> | status | down"; exit 2;;
  esac
  say "== ket qua: $PASS PASS, $FAIL FAIL ($(date -u +%Y-%m-%dT%H:%M:%SZ)). File: $OUT"
}

if [ "${CHAOS_SOURCE_ONLY:-}" != 1 ]; then main "$@"; fi
