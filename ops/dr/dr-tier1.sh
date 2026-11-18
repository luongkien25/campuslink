#!/bin/bash
# dr-tier1.sh - FR-INF-25 tang 1: Cinder snapshot -> volume moi -> DB VM thu (do RTO). Khong dung toi DB that.
# Chay tren A:  sudo bash dr-tier1.sh run     (khoang 8-12 phut, tu don)    |   sudo bash dr-tier1.sh down  (don neu bi ngat)
# Chi snapshot (crash-consistent) campus-db-data bang member; VM thu ten dr-t1-vm, KHONG FIP, KHONG SSH, doc ket qua qua console log.
# Khong in secret: chi in ten DB, so dong, so lan khop link thu.
set -u
umask 077
U=${LAB_USER:-tv2}
OWNER=${SUDO_USER:-root}
HOMEDIR=$(getent passwd "$OWNER" | cut -d: -f6)
OUT=${OUT:-$HOMEDIR/dr-tier1-$(date -u +%Y%m%d).txt}
SRCVOL=campus-db-data
AZ=${DR_AZ:-campus-az-a}
KNOWN=${KNOWN_SHORTCODE:-tv2g4-20261111}
WAIT_READY=${WAIT_READY:-900}
PASS=0; FAIL=0

say(){ echo "$*" | tee -a "$OUT"; }
ok(){ PASS=$((PASS+1)); say "PASS  $*"; }
bad(){ FAIL=$((FAIL+1)); say "FAIL  $*"; }
info(){ say "INFO  $*"; }
OSM(){ sudo -u "$U" -H env OS_CLOUD="campus-$U" openstack "$@"; }
OSA(){ sudo -u stack -H bash -c 'export PATH=/opt/stack/data/venv/bin:$PATH; . /opt/stack/devstack/openrc admin admin >/dev/null 2>&1; openstack "$@"' _ "$@"; }
now(){ date +%s.%N; }
dur(){ awk -v a="$1" -v b="$2" 'BEGIN{printf "%.0f", b-a}'; }

wait_status(){ # $1=loai(volume|snapshot) $2=ten $3=trang thai mong doi $4=toi da giay
  local i s cmd
  for i in $(seq 1 $(( $4 / 3 ))); do
    if [ "$1" = snapshot ]; then s=$(OSM volume snapshot show "$2" -f value -c status 2>/dev/null); else s=$(OSM volume show "$2" -f value -c status 2>/dev/null); fi
    [ "$s" = "$3" ] && return 0
    case "$s" in error*) return 1;; esac
    sleep 3
  done
  return 1
}

cleanup(){
  local i left=0
  info "== don: server, volume, snapshot dr-t1-*"
  OSM server delete --wait dr-t1-vm >/dev/null 2>&1
  OSM volume delete dr-t1-vol >/dev/null 2>&1
  for i in $(seq 1 40); do OSM volume show dr-t1-vol >/dev/null 2>&1 || break; sleep 3; done
  OSM volume snapshot delete dr-t1-snap >/dev/null 2>&1
  for i in $(seq 1 40); do OSM volume snapshot show dr-t1-snap >/dev/null 2>&1 || break; sleep 3; done
  OSM server show dr-t1-vm >/dev/null 2>&1 && left=$((left+1))
  OSM volume show dr-t1-vol >/dev/null 2>&1 && left=$((left+1))
  OSM volume snapshot show dr-t1-snap >/dev/null 2>&1 && left=$((left+1))
  if [ "$left" = 0 ]; then ok "don: khong con tai nguyen dr-t1-*"; else bad "don: con $left tai nguyen dr-t1-* (chay lai: sudo bash $0 down)"; fi
}

run(){
  local W t0 tsnap tvol tvm tatt tready rto size snapat st
  info "== FR-INF-25 tang 1: snapshot $SRCVOL -> volume moi -> DB VM thu (AZ cua VM thu: $AZ)"
  if OSM server show dr-t1-vm >/dev/null 2>&1 || OSM volume show dr-t1-vol >/dev/null 2>&1 || OSM volume snapshot show dr-t1-snap >/dev/null 2>&1; then
    bad "con tai nguyen dr-t1-* tu lan truoc (chay: sudo bash $0 down)"; return 1
  fi
  st=$(OSM volume show "$SRCVOL" -f value -c status 2>/dev/null)
  size=$(OSM volume show "$SRCVOL" -f value -c size 2>/dev/null)
  info "nguon: $SRCVOL status=${st:-?} size=${size:-?} GiB"
  [ -n "$size" ] || { bad "khong doc duoc $SRCVOL (member $U)"; return 1; }
  OSM limits show --absolute 2>/dev/null | grep -i -E 'volume|gigabyte|instance' | while read -r l; do info "  $l"; done

  W=$(mktemp -d); chmod 755 "$W"
  cat > "$W/ud.yaml" <<'EOF'
#cloud-config
write_files:
  - path: /usr/local/sbin/dr-test.sh
    permissions: '0700'
    content: |
      #!/bin/bash
      c(){ echo "DR-TEST $*" > /dev/console; }
      P="runuser -u postgres -- psql -h /tmp -p 5433 -Atc"
      c "START $(date -u +%T)"
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq >/dev/null 2>&1
      apt-get install -y -qq postgresql-16 >/dev/null 2>&1 || { c "FAIL apt install postgresql-16"; exit 1; }
      systemctl stop postgresql >/dev/null 2>&1
      c "APT-DONE $(date -u +%T)"
      for i in $(seq 1 180); do [ -e /dev/disk/by-label/campus-db-data ] && break; sleep 5; done
      [ -e /dev/disk/by-label/campus-db-data ] || { c "FAIL khong thay volume nhan campus-db-data"; exit 1; }
      mkdir -p /mnt/dr
      mount /dev/disk/by-label/campus-db-data /mnt/dr || { c "FAIL mount"; exit 1; }
      D=/mnt/dr/16/main
      [ -f $D/PG_VERSION ] || { c "FAIL khong co PG_VERSION trong $D; thu muc goc: $(ls /mnt/dr | tr ' ' ',' | tr -d '\n')"; exit 1; }
      c "MOUNT-OK PG_VERSION=$(cat $D/PG_VERSION) $(date -u +%T)"
      c "LSBLK $(lsblk -l -n -o NAME,SIZE,FSTYPE,LABEL | tr '\n' ';')"
      c "HOST $(hostname)"
      chown -R postgres:postgres /mnt/dr/16
      printf '%s\n' "port = 5433" "listen_addresses = ''" "unix_socket_directories = '/tmp'" "hba_file = '/etc/dr-hba.conf'" "ident_file = '/etc/dr-ident.conf'" > /etc/dr-pg.conf
      echo 'local all all trust' > /etc/dr-hba.conf
      : > /etc/dr-ident.conf
      runuser -u postgres -- /usr/lib/postgresql/16/bin/postgres -D $D -c config_file=/etc/dr-pg.conf > /var/log/dr-pg.log 2>&1 &
      for i in $(seq 1 60); do $P 'select 1' >/dev/null 2>&1 && break; sleep 2; done
      $P 'select 1' >/dev/null 2>&1 || { c "FAIL postgres khong len: $(tail -n 3 /var/log/dr-pg.log | tr '\n' ' ')"; exit 1; }
      c "PG-UP $(date -u +%T)"
      c "DBS $($P "select string_agg(datname, ',') from pg_database where not datistemplate" -d postgres 2>&1)"
      N=$($P 'select count(*) from short_urls' -d shlink 2>&1)
      V=$($P 'select count(*) from visits' -d shlink 2>&1)
      K=$($P "select count(*) from short_urls where short_code = '__KNOWN__'" -d shlink 2>&1)
      c "COUNTS short_urls=$N visits=$V known=$K"
      c "READY $(date -u +%T)"
runcmd:
  - [ bash, /usr/local/sbin/dr-test.sh ]
EOF
  sed -i "s/__KNOWN__/$KNOWN/" "$W/ud.yaml"
  chmod 644 "$W/ud.yaml"

  t0=$(now)
  info "1. snapshot $SRCVOL (--force: dang gan vao campus-db, crash-consistent)"
  OSM volume snapshot create --volume "$SRCVOL" --force dr-t1-snap >"$W/o1" 2>&1 || { bad "tao snapshot loi: $(head -c 300 "$W/o1" | tr '\n' ' ')"; rm -rf "$W"; cleanup; return 1; }
  wait_status snapshot dr-t1-snap available 300 || { bad "snapshot khong available"; rm -rf "$W"; cleanup; return 1; }
  tsnap=$(now); snapat=$(OSM volume snapshot show dr-t1-snap -f value -c created_at 2>/dev/null)
  ok "snapshot available sau $(dur "$t0" "$tsnap") s (created_at=$snapat)"

  info "2. volume moi tu snapshot"
  OSM volume create --snapshot dr-t1-snap --size "$size" dr-t1-vol >"$W/o2" 2>&1 || { bad "tao volume tu snapshot loi: $(head -c 300 "$W/o2" | tr '\n' ' ')"; rm -rf "$W"; cleanup; return 1; }
  wait_status volume dr-t1-vol available 300 || { bad "volume tu snapshot khong available"; rm -rf "$W"; cleanup; return 1; }
  tvol=$(now); ok "volume dr-t1-vol available sau $(dur "$t0" "$tvol") s (tu luc bat dau)"

  info "3. DB VM thu (campus.db, $AZ, campus-db-sg, khong FIP, khong SSH)"
  OSM server create --flavor campus.db --image ubuntu-noble-base --network campus-net --security-group campus-db-sg \
      --availability-zone "$AZ" --user-data "$W/ud.yaml" --property campus_role=dr-test --wait -f value -c id dr-t1-vm >"$W/o3" 2>&1 \
      || { bad "tao dr-t1-vm loi: $(head -c 300 "$W/o3" | tr '\n' ' ')"; rm -rf "$W"; cleanup; return 1; }
  tvm=$(now); ok "dr-t1-vm ACTIVE sau $(dur "$t0" "$tvm") s"
  srvid=$(head -n 1 "$W/o3" | tr -d ' ')
  host=$(OSA server show "$srvid" -f json 2>/dev/null | grep -o -E '"(OS-EXT-SRV-ATTR:host|compute_host)": *"[^"]*"' | head -1 | sed -E 's/.*: *"([^"]*)"/\1/')
  want="campus-${AZ##*-}"
  if [ -z "$host" ]; then info "khong doc duoc host cua dr-t1-vm bang quyen admin (id=${srvid:-?})"
  elif [ "$host" = "$want" ]; then ok "dr-t1-vm chay tren host $host (dung voi AZ $AZ)"
  else bad "dr-t1-vm chay tren host $host, mong doi $want (AZ $AZ)"; fi

  info "4. gan volume khoi phuc vao VM thu"
  OSM server add volume dr-t1-vm dr-t1-vol >"$W/o4" 2>&1 || { bad "gan volume loi: $(head -c 300 "$W/o4" | tr '\n' ' ')"; rm -rf "$W"; cleanup; return 1; }
  wait_status volume dr-t1-vol in-use 120 || { bad "volume khong in-use sau khi gan"; rm -rf "$W"; cleanup; return 1; }
  tatt=$(now); ok "volume in-use sau $(dur "$t0" "$tatt") s"

  info "5. doi console log co DR-TEST READY (toi da ${WAIT_READY}s)"
  tready=""
  while [ "$(dur "$tatt" "$(now)")" -lt "$WAIT_READY" ]; do
    OSM console log show --lines 400 dr-t1-vm 2>/dev/null | grep -a 'DR-TEST' > "$W/con.txt"
    if grep -q 'DR-TEST READY' "$W/con.txt"; then tready=$(now); break; fi
    if grep -q 'DR-TEST FAIL' "$W/con.txt"; then break; fi
    sleep 10
  done
  [ -s "$W/con.txt" ] && while read -r l; do info "console: $l"; done < "$W/con.txt"
  if [ -n "$tready" ]; then
    rto=$(dur "$t0" "$tready")
    ok "PostgreSQL len tren du lieu khoi phuc: RTO do duoc (tu luc bat dau snapshot) = ${rto} s"
    grep -q 'COUNTS short_urls=[0-9]' "$W/con.txt" && ok "truy van duoc bang short_urls tren ban khoi phuc" || bad "khong doc duoc short_urls (xem dong COUNTS)"
    grep -q -E 'known=1([^0-9]|$)' "$W/con.txt" && ok "link thu $KNOWN co trong ban khoi phuc" || info "link thu $KNOWN khong thay (known != 1); khong coi la FAIL"
  else
    bad "khong thay DR-TEST READY (doc dong FAIL/console o tren)"
  fi
  rm -rf "$W"
  cleanup
}

if [ "$(id -u)" != 0 ]; then echo "Chay bang: sudo bash $0 run|down"; exit 2; fi
trap 'chown "$OWNER" "$OUT" 2>/dev/null' EXIT
say "== dr-tier1 ${1:-} bat dau $(date -u +%Y-%m-%dT%H:%M:%SZ) tren $(hostname)"
case "${1:-}" in
  run) run;;
  down) cleanup;;
  *) echo "Dung: sudo bash $0 run | down"; exit 2;;
esac
say "== ket qua: $PASS PASS, $FAIL FAIL ($(date -u +%Y-%m-%dT%H:%M:%SZ)). File: $OUT"
