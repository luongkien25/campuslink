#!/usr/bin/env bash
# CampusLink - do drain visit (SRS O-07), Compose local. TV3.
# Ban N GET vao replica A, roi: none = khong dung | stop = SIGTERM ngay | kill = SIGKILL ngay.
# Dem visit qua replica B (DB chung). In: so GET, so visit ghi duoc, thoi gian visit du.
# Dung: ./drain-measure.sh <none|stop|kill> [N] [song_song]
set -uo pipefail

here=$(cd "$(dirname "$0")" && pwd)
cd "$here/../compose"
mode=${1:?none|stop|kill}; N=${2:-300}; P=${3:-20}
A=http://127.0.0.1:18080; B=http://127.0.0.1:18081
key=$(<secrets/api_key_tv3-admin)
UA='Mozilla/5.0 (X11; Linux x86_64) campuslink-drain'
slug="tv3-drain-${mode}-$(date -u +%Y%m%dt%H%M%Sz)"

curl -sS -o /dev/null -X POST "$B/rest/v3/short-urls" -H "X-Api-Key: $key" -H 'Content-Type: application/json' \
  --data "{\"longUrl\":\"https://example.org/drain\",\"customSlug\":\"$slug\",\"tags\":[\"campus-drain\"]}"

t_start=$(date +%s.%N)
ok=$(seq 1 "$N" | xargs -P "$P" -I{} curl -sS -o /dev/null -A "$UA" -w '%{http_code}\n' "$A/$slug" | grep -c '^302$')
t_last=$(date +%s.%N)

case $mode in
  stop) t0=$(date +%s.%N); docker compose stop shlink >/dev/null 2>&1; echo "stop mat $(echo "$(date +%s.%N) - $t0" | bc)s" ;;
  kill) docker compose kill shlink >/dev/null 2>&1 ;;
esac

count() { curl -sS "$B/rest/v3/short-urls/$slug/visits?itemsPerPage=1" -H "X-Api-Key: $key" | jq -r '.visits.pagination.totalItems'; }
got=0; t_full=""
for _ in $(seq 1 60); do
  got=$(count)
  if [[ $got == "$ok" ]]; then t_full=$(echo "$(date +%s.%N) - $t_last" | bc); break; fi
  sleep 0.5
done
echo "mode=$mode slug=$slug GET_302=$ok/$N tai=$(echo "$t_last - $t_start" | bc)s visit=$got mat=$((ok-got)) visit_du_sau=${t_full:-chua-du-sau-30s}s"

if [[ $mode != none ]]; then
  docker compose up -d shlink >/dev/null 2>&1
  for _ in $(seq 1 60); do [[ $(docker inspect -f '{{.State.Health.Status}}' campuslink-local-shlink-1) == healthy ]] && break; sleep 2; done
  sleep 3
  echo "sau khi A khoi dong lai: visit=$(count) (task trong bo nho co duoc lam lai khong)"
fi
