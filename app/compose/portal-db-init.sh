#!/bin/bash
# Compose local: tao role + DB campus_portal mot lan (postgres o day la superuser "shlink").
# Tren cum TV3 tao tren DB VM (H1b). Mat khau doc tu file, di qua stdin cua psql, khong qua argv.
set -euo pipefail
export PGPASSWORD="$(cat /run/secrets/db_password)"
pw="$(cat /run/secrets/portal_db_password)"
psql -h postgres -U shlink -d shlink -v ON_ERROR_STOP=1 -q <<SQL
SELECT 'CREATE ROLE campus_portal LOGIN CONNECTION LIMIT 10' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'campus_portal') \gexec
ALTER ROLE campus_portal PASSWORD '$pw';
SELECT 'CREATE DATABASE campus_portal OWNER campus_portal' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'campus_portal') \gexec
SQL
echo "OK role + DB campus_portal"
