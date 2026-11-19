#!/usr/bin/env bash
# CampusLink - ghi 2 secret core vao Swift campus-secrets/app/ (ADR-10, H1 muc 6). TV3.
# Chay tren host A: OS_CLOUD=campus-tv3 ./put-secrets.sh [probe]
#   probe : chi thu quyen ghi (tao roi xoa object app/_probe-tv3, khong co secret)
#   (trong): ghi app/db_password va app/redis_servers tu ~/campus-db-secrets, so etag voi md5 file
#   portal : (H1b) sinh portal_db_password, portal_db_url, portal_secret_key trong ~/campus-db-secrets neu chua co,
#            ghi app/portal_db_url va app/portal_secret_key (SRS 4.6). portal_db_password KHONG len Swift: chi dua
#            vao DB VM qua stdin (app/db/portal-db.sh); URL dung chung mat khau do.
# Khong in secret hay etag.
set -euo pipefail

: "${OS_CLOUD:?dat OS_CLOUD=campus-tv3}"
dir=${CAMPUS_DB_SECRETS:-$HOME/campus-db-secrets}
c=campus-secrets

if [[ ${1:-} == probe ]]; then
  f=$(mktemp); echo "probe tv3 $(date -u +%FT%TZ)" > "$f"
  openstack object create --name app/_probe-tv3 "$c" "$f" -f value -c object
  openstack object delete "$c" app/_probe-tv3 && echo "OK member ghi/xoa duoc trong $c"
  rm -f "$f"
  exit 0
fi

names="db_password redis_servers"
if [[ ${1:-} == portal ]]; then
  umask 077; install -d -m 700 "$dir"
  mk() { [[ -s $dir/$1 ]] && { echo "giu $dir/$1 (da co)"; return; }; printf '%s\n' "$2" > "$dir/$1"; chmod 600 "$dir/$1"; echo "tao $dir/$1"; }
  mk portal_db_password "$(openssl rand -hex 24)"
  mk portal_db_url "postgresql://campus_portal:$(<"$dir/portal_db_password")@10.20.0.10:5432/campus_portal"
  mk portal_secret_key "$(openssl rand -hex 32)"
  names="portal_db_url portal_secret_key"
fi

fails=0
for n in $names; do
  f=$dir/$n
  [[ -s $f ]] || { echo "FAIL thieu $f (chay render-user-data.sh truoc)"; exit 1; }
  openstack object create --name "app/$n" "$c" "$f" -f value -c object >/dev/null
  etag=$(openstack object show "$c" "app/$n" -f value -c etag)
  if [[ $etag == "$(md5sum < "$f" | cut -d' ' -f1)" ]]; then
    echo "OK $c/app/$n etag khop md5 file local ($(wc -c < "$f") byte)"
  else
    echo "FAIL $c/app/$n etag khong khop"; fails=$((fails+1))
  fi
done
exit $((fails > 0))
