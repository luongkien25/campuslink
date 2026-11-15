#!/bin/bash
# CampusLink - tao role + DB campus_portal tren DB VM (H1b, SRS 4.6, FR-APP-13). TV3.
# Chay tren DB VM bang root, mat khau qua STDIN (1 dong hex, khong qua argv, khong qua user-data):
#   scp app/db/portal-db.sh campus-db:                       # (stdin danh cho mat khau nen khong dung bash -s)
#   ssh campus-a 'cat ~/campus-db-secrets/portal_db_password' | ssh campus-db 'sudo bash portal-db.sh'
# Lam gi (chay lai duoc, khong xoa du lieu):
#   1. role campus_portal LOGIN, CONNECTION LIMIT 10, dat lai mat khau tu stdin
#   2. DB campus_portal OWNER campus_portal (neu chua co), REVOKE CONNECT tu PUBLIC
#   3. pg_hba: "host campus_portal campus_portal 10.20.0.0/24 scram-sha-256" (neu chua co), reload
# Khong in mat khau. Ngan sach ket noi: max_connections 50 = shlink 15 + campus_portal 10 + du phong (H1 muc 5.2).
set -euo pipefail
umask 077

IFS= read -r pw || true
[[ $pw =~ ^[0-9a-f]{32,}$ ]] || { echo "FAIL stdin phai la mat khau hex (>= 32 ky tu)"; exit 1; }

hba=${PG_HBA:-/etc/postgresql/16/main/pg_hba.conf}   # ghi de khi thu local
line="host campus_portal campus_portal 10.20.0.0/24 scram-sha-256"

runuser -u postgres -- psql -q -v ON_ERROR_STOP=1 <<EOF
\set pw '$pw'
SELECT 'CREATE ROLE campus_portal LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'campus_portal') \gexec
ALTER ROLE campus_portal LOGIN CONNECTION LIMIT 10 PASSWORD :'pw';
SELECT 'CREATE DATABASE campus_portal OWNER campus_portal' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'campus_portal') \gexec
REVOKE CONNECT ON DATABASE campus_portal FROM PUBLIC;
EOF
unset pw
echo "OK role + DB campus_portal"

if grep -qxF "$line" "$hba"; then
  echo "OK pg_hba da co dong campus_portal"
else
  cp -p "$hba" "$hba.bak-$(date -u +%Y%m%dT%H%M%SZ)"
  echo "$line" >> "$hba"
  echo "OK them dong pg_hba campus_portal"
fi
runuser -u postgres -- psql -At -c "SELECT pg_reload_conf()" >/dev/null
# Kiem: rule hba da nap, role/DB ton tai (khong in mat khau)
runuser -u postgres -- psql -At -F ' ' -c "SELECT 'hba', line_number, database[1], user_name[1], address, auth_method FROM pg_hba_file_rules WHERE 'campus_portal' = ANY(database)"
runuser -u postgres -- psql -At -F ' ' -c "SELECT 'role', rolname, rolconnlimit, rolcanlogin FROM pg_roles WHERE rolname = 'campus_portal'"
runuser -u postgres -- psql -At -F ' ' -c "SELECT 'db', datname, pg_get_userbyid(datdba) FROM pg_database WHERE datname = 'campus_portal'"
