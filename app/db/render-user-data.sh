#!/usr/bin/env bash
# CampusLink - sinh mat khau that cho DB VM va render user-data (FR-INF-12, ADR-10). TV3.
# Chay tren host A bang user tv3 (khong can sudo). Khong in secret.
# Ket qua trong ~/campus-db-secrets/ (thu muc 700, file 600):
#   db_password, redis_password, redis_servers  -> put-secrets.sh ghi vao Swift campus-secrets/app/
#   user-data.yaml                              -> dung cho openstack server create, xoa ngay sau do
# Da co thu muc thi dung lai (tranh doi mat khau khi DB da tao); --force de sinh lai.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
dir=${CAMPUS_DB_SECRETS:-$HOME/campus-db-secrets}

if [[ -e $dir && ${1:-} != --force ]]; then
  echo "Da co $dir, khong sinh lai (dung --force neu DB VM chua tao)."
  exit 1
fi

umask 077
mkdir -p "$dir"
chmod 700 "$dir"

# Hex: khong can urlencode trong URI Redis, khong can escape trong SQL (H1 muc 6)
db_password=$(openssl rand -hex 24)
redis_password=$(openssl rand -hex 24)
printf '%s\n' "$db_password" > "$dir/db_password"
printf '%s\n' "$redis_password" > "$dir/redis_password"
printf 'tcp://default:%s@10.20.0.10:6379\n' "$redis_password" > "$dir/redis_servers"

# Thay bang expansion cua bash (khong dua mat khau vao argv cua sed)
t=$(<"$here/user-data.tmpl.yaml")
t=${t//REPLACE_DB_PASSWORD/$db_password}
t=${t//REPLACE_REDIS_PASSWORD/$redis_password}
printf '%s\n' "$t" > "$dir/user-data.yaml"

left=$(grep -c REPLACE_ "$dir/user-data.yaml" || true)
echo "OK $dir: db_password redis_password redis_servers user-data.yaml (con REPLACE_: $left)"
ls -l "$dir" | awk 'NR>1{print "  "$1, $9}'
