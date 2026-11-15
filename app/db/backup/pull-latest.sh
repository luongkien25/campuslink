#!/usr/bin/env bash
# CampusLink - chep ban dump moi nhat tu Swift ve may ca nhan va kiem sha256 (FR-INF-15 "1 ban ve may nhom", NFR-11). TV3.
# Chay tren laptop: ./pull-latest.sh [thu-muc-dich]   (mac dinh ~/campuslink-backups)
# Di qua A bang credential Keystone cua ban (OS_CLOUD tren A, mac dinh campus-tv3).
set -euo pipefail
dest=${1:-$HOME/campuslink-backups}
cloud=${OS_CLOUD_A:-campus-tv3}
mkdir -p "$dest"

name=$(ssh campus-a "OS_CLOUD=$cloud openstack object list campus-backups --prefix db/shlink- -f value -c Name" \
  | grep '\.dump$' | sort | tail -n1)
[[ -n $name ]] || { echo "FAIL khong co dump trong campus-backups/db/"; exit 1; }
base=${name##*/}
ssh campus-a "set -e; d=\$(mktemp -d); cd \$d; OS_CLOUD=$cloud openstack object save --file $base campus-backups $name; \
  OS_CLOUD=$cloud openstack object save --file $base.sha256 campus-backups $name.sha256; tar cf - $base $base.sha256; rm -rf \$d" \
  | tar xf - -C "$dest"
(cd "$dest" && sha256sum -c "$base.sha256")
echo "OK $dest/$base ($(stat -c %s "$dest/$base") byte)"
