#!/usr/bin/env bash
# Sinh secret NGAU NHIEN cho Compose local vao app/compose/secrets/ (bi .gitignore chan).
# Chi dung tren may ca nhan. Khong dung secret nay cho cum that.
# Chay lai khi da co secret thi bo qua, tru khi them --force (phai xoa volume Postgres/Redis: docker compose down -v).
set -euo pipefail

cd "$(dirname "$0")"
dir=secrets

if [[ -d $dir && ${1:-} != --force ]]; then
  echo "Da co $dir/, bo qua (dung --force de sinh lai)."
  exit 0
fi

umask 077
mkdir -p "$dir"
chmod 700 "$dir"

# Hex nen khong can urlencode trong URI Redis
db_password=$(openssl rand -hex 24)
redis_password=$(openssl rand -hex 24)

printf '%s\n' "$db_password" > "$dir/db_password"
printf 'tcp://default:%s@redis:6379\n' "$redis_password" > "$dir/redis_servers"
# Redis khong doc mat khau tu file, nen dung file cau hinh phu
printf 'requirepass %s\n' "$redis_password" > "$dir/redis.conf"
# Cho redis-cli PING co xac thuc (REDISCLI_AUTH doc tu file nay khi kiem)
printf '%s\n' "$redis_password" > "$dir/redis_password"

# Mode 0444 theo SRS 4.3: container Shlink chay uid 1001, phai doc duoc file bind-mount
chmod 444 "$dir"/*
echo "Da sinh secret trong $dir/ (khong in gia tri)."
