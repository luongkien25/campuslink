#!/bin/bash
# dr-tier2.sh - FR-INF-25 tang 2: dump trong Swift (campus-backups/db/) -> PostgreSQL 16 sach -> campus_restore_test; do RTO.
# Chay tren A:  sudo bash dr-tier2.sh run     (khoang 4-6 phut)    |   sudo bash dr-tier2.sh down  (don neu bi ngat)
# Khong dung toi DB VM that va khong can SSH/VM nhay/FIP: doc dump bang quyen member cua TV3 (sudo -u tv3, nhu cac script khac),
# restore vao cum PostgreSQL tam "dr2" (cong 54322, chi localhost) tren A. KHONG dung credential campus-db-backup (chi nam tren DB VM).
# Khong in noi dung DB: chi so dong, ten migration, ten slug thu. File dump nam trong thu muc root 0700, xoa khi xong.
# RTO do tu luc bat dau liet ke Swift den luc truy van duoc DB da khoi phuc; KHONG gom thoi gian dung DB VM/PostgreSQL (do rieng).
set -u
umask 077
cd /tmp
U=${DR_USER:-tv3}
OWNER=${SUDO_USER:-root}
HOMEDIR=$(getent passwd "$OWNER" | cut -d: -f6)
OUT=${OUT:-$HOMEDIR/dr-tier2-$(date -u +%Y%m%d).txt}
CONT=${CONTAINER:-campus-backups}
PFX=${PREFIX:-db/}
CL=dr2
PORT=54322
TARGET=campus_restore_test
KNOWN=${KNOWN_SHORTCODE:-tv2g4-20261111}
FLAG=/var/lib/dr-tier2.installed-pg
WORK=/var/tmp/dr-tier2
PASS=0; FAIL=0

say(){ echo "$*" | tee -a "$OUT"; }
ok(){ PASS=$((PASS+1)); say "PASS  $*"; }
bad(){ FAIL=$((FAIL+1)); say "FAIL  $*"; }
info(){ say "INFO  $*"; }
OSM(){ sudo -u "$U" -H env OS_CLOUD="campus-$U" openstack "$@"; }
now(){ date +%s.%N; }
dur(){ awk -v a="$1" -v b="$2" 'BEGIN{printf "%.1f", b-a}'; }
PGQ(){ runuser -u postgres -- psql -p "$PORT" -At -v ON_ERROR_STOP=1 -d "$1" -c "$2"; }

swift_get(){ # $1=ten object  $2=file dich. Thu ghi ra stdout (--file -); neu loi thi luu vao thu muc cua $U roi cat
  local d=/tmp/dr-tier2-$U rc
  OSM object save --file - "$CONT" "$1" > "$2" 2>>"$WORK/get.err" && [ -s "$2" ] && return 0
  rm -rf "$d"; install -d -o "$U" -m 700 "$d"
  OSM object save --file "$d/f" "$CONT" "$1" 2>>"$WORK/get.err"; rc=$?
  [ "$rc" = 0 ] && cat "$d/f" > "$2"; rc=$?
  rm -rf "$d"
  [ "$rc" = 0 ] && [ -s "$2" ]
}

has_cluster(){ command -v pg_lsclusters >/dev/null 2>&1 && pg_lsclusters 2>/dev/null | awk '{print $1" "$2}' | grep -q "^16 $CL$"; }

prepare_pg(){
  local tp
  if has_cluster; then bad "con cum $CL tu lan truoc (chay: sudo bash $0 down)"; return 1; fi
  if [ ! -x /usr/lib/postgresql/16/bin/initdb ]; then
    info "A chua co may chu PostgreSQL 16 (thieu initdb; pg_createcluster co the da co san tu goi postgresql-common): cai postgresql-16 (tam, se go khi xong). Khong tinh vao RTO."
    : > "$FLAG"
    for p in postgresql-16 postgresql-client-16; do dpkg -s "$p" >/dev/null 2>&1 || echo "$p" >> "$FLAG"; done
    info "goi se cai them va go lai khi xong: $(tr '\n' ' ' < "$FLAG")"
    tp=$(now)
    apt-get update -qq >"$WORK/apt.log" 2>&1
    NEEDRESTART_MODE=a DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-16 postgresql-client-16 >>"$WORK/apt.log" 2>&1 \
      || { bad "apt install postgresql-16 loi: $(tail -c 300 "$WORK/apt.log" | tr '\n' ' ')"; return 1; }
    if pg_lsclusters 2>/dev/null | awk '{print $1" "$2}' | grep -q '^16 main$'; then pg_dropcluster --stop 16 main >/dev/null 2>&1; info "da bo cum 16/main do goi vua tao"; fi
    ok "cai postgresql-16 trong $(dur "$tp" "$(now)") s"
  fi
  tp=$(now)
  pg_createcluster 16 "$CL" --port "$PORT" --start >"$WORK/cc.log" 2>&1 || { bad "pg_createcluster 16 $CL loi: $(tail -c 300 "$WORK/cc.log" | tr '\n' ' ')"; return 1; }
  local i
  for i in $(seq 1 30); do pg_isready -q -p "$PORT" && break; sleep 1; done
  pg_isready -q -p "$PORT" && ok "cum $CL san sang trong $(dur "$tp" "$(now)") s (cong $PORT)" || { bad "cum $CL khong san sang"; return 1; }
  info "server_version: $(PGQ postgres 'show server_version')"
}

run(){
  local T0 T1 T2 T3 T4 T5 names latest base objsz etag_srv etag_loc sha_want sha_got sc vi mg slug rc
  mkdir -p "$WORK"; chmod 700 "$WORK"
  info "== FR-INF-25 tang 2: $CONT/$PFX -> PostgreSQL 16 sach (cum $CL tren A) -> $TARGET"
  info "may: $(hostname), boot $(uptime -s), doc Swift bang member $U"
  prepare_pg || { down; return 1; }

  T0=$(now)
  names=$(OSM object list "$CONT" --prefix "${PFX}shlink-" -f value -c Name 2>"$WORK/list.err")
  latest=$(echo "$names" | grep '[.]dump$' | sort | tail -1)
  if [ -z "$latest" ]; then bad "khong liet ke duoc dump trong $CONT/$PFX (member $U): $(head -c 300 "$WORK/list.err" | tr '\n' ' ')"; down; return 1; fi
  latest=${DUMP:-$latest}
  base=${latest##*/}
  T1=$(now)
  info "dump moi nhat: $latest (liet ke $(dur "$T0" "$T1") s; $(echo "$names" | grep -c '[.]dump$') ban .dump trong Swift)"

  : > "$WORK/get.err"
  swift_get "$latest" "$WORK/$base" || { bad "tai $latest loi: $(head -c 300 "$WORK/get.err" | tr '\n' ' ')"; down; return 1; }
  swift_get "$latest.sha256" "$WORK/$base.sha256" || { bad "tai $latest.sha256 loi: $(head -c 300 "$WORK/get.err" | tr '\n' ' ')"; down; return 1; }
  T2=$(now)
  objsz=$(stat -c %s "$WORK/$base")
  info "tai dump + .sha256: $objsz byte trong $(dur "$T1" "$T2") s"

  etag_srv=$(OSM object show "$CONT" "$latest" -f value -c etag 2>/dev/null)
  etag_loc=$(md5sum < "$WORK/$base" | cut -d' ' -f1)
  if [ -n "$etag_srv" ] && [ "$etag_srv" = "$etag_loc" ]; then ok "ETag (md5) Swift khop file tai ve"; else bad "ETag Swift '$etag_srv' khac md5 file '$etag_loc'"; fi
  sha_want=$(cut -d' ' -f1 "$WORK/$base.sha256")
  sha_got=$(sha256sum < "$WORK/$base" | cut -d' ' -f1)
  T3=$(now)
  if [ "$sha_want" = "$sha_got" ]; then ok "sha256 khop object .sha256 ($sha_got)"; else bad "sha256 KHONG khop: object $sha_want, file $sha_got"; down; return 1; fi

  runuser -u postgres -- psql -p "$PORT" -q -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS $TARGET WITH (FORCE)" -c "CREATE DATABASE $TARGET" >"$WORK/db.log" 2>&1 \
    || { bad "tao $TARGET loi: $(tail -c 300 "$WORK/db.log" | tr '\n' ' ')"; down; return 1; }
  runuser -u postgres -- pg_restore -p "$PORT" --no-owner --no-acl --exit-on-error -d "$TARGET" < "$WORK/$base" >"$WORK/restore.log" 2>&1; rc=$?
  T4=$(now)
  if [ "$rc" = 0 ]; then ok "pg_restore vao $TARGET rc=0 trong $(dur "$T3" "$T4") s"; else bad "pg_restore rc=$rc: $(tail -c 400 "$WORK/restore.log" | tr '\n' ' ')"; down; return 1; fi

  sc=$(PGQ "$TARGET" 'SELECT count(*) FROM short_urls')
  vi=$(PGQ "$TARGET" 'SELECT count(*) FROM visits')
  mg=$(PGQ "$TARGET" "SELECT CASE WHEN to_regclass('public.migrations') IS NOT NULL THEN (SELECT max(version) FROM migrations) END")
  slug=$(PGQ "$TARGET" "SELECT coalesce((SELECT original_url FROM short_urls WHERE short_code = '$KNOWN'), 'KHONG CO')")
  T5=$(now)
  info "$TARGET: short_urls=$sc visits=$vi migration=$mg"
  info "slug $KNOWN -> $slug"
  [ "${sc:-0}" -ge 1 ] 2>/dev/null && ok "short_urls >= 1 trong ban khoi phuc" || bad "short_urls rong hoac khong doc duoc"
  [ "$slug" != "KHONG CO" ] && [ -n "$slug" ] && ok "slug $KNOWN co trong ban khoi phuc" || bad "slug $KNOWN khong co"
  [ -n "$mg" ] && ok "co phien ban migration Shlink" || bad "khong doc duoc migration"
  info "TV3 bao (12/11): short_urls=1 visits=2 migration=ShlinkMigrations/Version20260607082210 (khac vi dump moi hon thi khong sao)"
  info "RTO tang 2 (liet ke Swift -> truy van duoc ban khoi phuc): $(dur "$T0" "$T5") s"
  info "  gom: liet ke $(dur "$T0" "$T1") s, tai $(dur "$T1" "$T2") s, kiem etag+sha256 $(dur "$T2" "$T3") s, restore $(dur "$T3" "$T4") s, kiem so dong $(dur "$T4" "$T5") s"
  info "  chua gom: dung DB VM va cai PostgreSQL (xem tang 1: 124-158 s cho VM thu tu snapshot), dua ve IP 10.20.0.10, cau hinh app (TV3, runbook db-vm.md muc 8)"

  info "== kiem phat hien dump hong (khong tinh RTO)"
  cp "$WORK/$base" "$WORK/bad.dump"; printf 'x' >> "$WORK/bad.dump"
  if [ "$(sha256sum < "$WORK/bad.dump" | cut -d' ' -f1)" != "$sha_want" ]; then ok "dump bi sua 1 byte -> sha256 khong khop (phat hien duoc)"; else bad "dump bi sua nhung sha256 van khop?"; fi

  down
}

down(){
  local left=0
  info "== don"
  if has_cluster; then pg_dropcluster --stop 16 "$CL" >/dev/null 2>&1; fi
  has_cluster && left=$((left+1))
  rm -rf "$WORK"
  [ -e "$WORK" ] && left=$((left+1))
  if [ -f "$FLAG" ]; then
    if [ "${KEEP_PG:-0}" = 1 ]; then info "KEEP_PG=1: giu postgresql-16 da cai"
    else
      if [ -s "$FLAG" ]; then
        info "go cac goi do script cai: $(tr '\n' ' ' < "$FLAG")"
        # shellcheck disable=SC2046
        NEEDRESTART_MODE=a DEBIAN_FRONTEND=noninteractive apt-get purge -y -qq $(cat "$FLAG") >/dev/null 2>&1
        for p in $(cat "$FLAG"); do dpkg -s "$p" >/dev/null 2>&1 && left=$((left+1)); done
      fi
      rm -f "$FLAG"
    fi
  fi
  if [ "$left" = 0 ]; then ok "don: khong con cum $CL, thu muc tam, goi PostgreSQL do script cai"; else bad "don: con $left muc (chay lai: sudo bash $0 down)"; fi
}

on_exit(){ chown "$OWNER" "$OUT" 2>/dev/null; }

main(){
  if [ "$(id -u)" != 0 ]; then echo "Chay bang: sudo bash $0 <run|down>"; exit 2; fi
  trap on_exit EXIT
  trap 'say "NGAT: don"; mkdir -p "$WORK"; down; exit 130' INT TERM
  say "== dr-tier2 ${1:-} bat dau $(date -u +%Y-%m-%dT%H:%M:%SZ) tren $(hostname)"
  case "${1:-}" in
    run) run;;
    down) down;;
    *) echo "Dung: sudo bash $0 run | down"; exit 2;;
  esac
  say "== ket qua: $PASS PASS, $FAIL FAIL ($(date -u +%Y-%m-%dT%H:%M:%SZ)). File: $OUT"
}

main "$@"
