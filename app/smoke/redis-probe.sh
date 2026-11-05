#!/bin/sh
# CampusLink - probe Redis PING co xac thuc cho readiness (FR-INF-09). TV3.
# Chi doc file redis_servers dang tcp://<user>:<mat-khau-hex>@<host>:<port>; khong in mat khau.
# In PONG va exit 0 khi dung; in FAIL va exit 1 khi khac (redis-cli tra exit 0 ca khi sai mat khau).
# Dung: redis-probe.sh [file]   (mac dinh /run/secrets/redis_servers). Can redis-cli (goi redis-tools).
f=${1:-/run/secrets/redis_servers}
u=$(cat "$f") || { echo FAIL; exit 1; }
hp=${u##*@}
pw=${u#tcp://*:}; pw=${pw%@*}
out=$(REDISCLI_AUTH="$pw" timeout 5 redis-cli -h "${hp%:*}" -p "${hp##*:}" --no-auth-warning ping 2>&1)
if [ "$out" = PONG ]; then echo PONG; exit 0; fi
echo FAIL
exit 1
