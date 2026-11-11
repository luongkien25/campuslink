#!/usr/bin/env bash
# CampusLink - ghi 2 secret core vao Swift campus-secrets/app/ (ADR-10, H1 muc 6). TV3.
# Chay tren host A: OS_CLOUD=campus-tv3 ./put-secrets.sh [probe]
#   probe : chi thu quyen ghi (tao roi xoa object app/_probe-tv3, khong co secret)
#   (trong): ghi app/db_password va app/redis_servers tu ~/campus-db-secrets, so etag voi md5 file
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

fails=0
for n in db_password redis_servers; do
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
