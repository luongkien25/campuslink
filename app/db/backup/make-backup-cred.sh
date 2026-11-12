#!/usr/bin/env bash
# CampusLink - tao application credential cho backup DB (FR-INF-15). TV3.
# Chay tren host A: OS_CLOUD=campus-tv3 ./make-backup-cred.sh
# Access rules (O-14): chi object-store, chi container campus-backups:
#   PUT/GET/HEAD/DELETE  /v1/AUTH_<project>/campus-backups/db/*   (dump + .sha256, retention)
#   GET                  /v1/AUTH_<project>/campus-backups        (liet ke de tim ban moi nhat / retention)
# Ghi ~/campus-backup-cred (0600, 2 dong id= va secret=), KHONG in secret. Da co file thi dung lai.
set -euo pipefail
: "${OS_CLOUD:?dat OS_CLOUD=campus-tv3}"
out=${CAMPUS_BACKUP_CRED:-$HOME/campus-backup-cred}
name=${CRED_NAME:-campus-db-backup}
exp=${CRED_EXPIRES:-2026-12-31T00:00:00}
[[ -e $out ]] && { echo "Da co $out, khong tao lai."; exit 1; }

proj=$(openstack token issue -f value -c project_id)
p="/v1/AUTH_$proj/campus-backups"
rules=$(printf '[{"service":"object-store","method":"%s","path":"%s/db/*"},' PUT "$p" GET "$p" HEAD "$p" DELETE "$p")
rules="${rules}{\"service\":\"object-store\",\"method\":\"GET\",\"path\":\"$p\"}]"

umask 077
tmp=$(mktemp)
openstack application credential create "$name" --expiration "$exp" \
  --description "CampusLink backup DB VM -> campus-backups/db (FR-INF-15, TV3)" \
  --access-rules "$rules" -f json > "$tmp"
python3 - "$tmp" "$out" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
with open(sys.argv[2], "w") as f:
    f.write(f"id={d['id']}\nsecret={d['secret']}\n")
print(f"OK credential {d['name']} id={d['id']} het han {d.get('expires_at')}, {len(d.get('access_rules') or [])} access rule")
PY
rm -f "$tmp"
ls -l "$out" | awk '{print $1, $NF}'
