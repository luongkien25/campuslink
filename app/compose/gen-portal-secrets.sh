#!/usr/bin/env bash
# Sinh secret NGAU NHIEN cho campus-portal tren Compose local (FR-APP-13, SRS 4.6). Chi tao file con thieu.
# Khong dung cho cum: tren cum secret nam trong Swift campus-secrets/app/ (ADR-10, H1b).
set -euo pipefail
cd "$(dirname "$0")"
dir=secrets
[[ -d $dir ]] || { echo "Chay ./gen-secrets.sh truoc"; exit 1; }
umask 077
mk() { [[ -e $dir/$1 ]] && return; printf '%s\n' "$2" > "$dir/$1"; chmod 444 "$dir/$1"; echo "tao $dir/$1"; }
mk portal_db_password "$(openssl rand -hex 24)"
# URL dung chung mat khau voi file tren
mk portal_db_url "postgresql://campus_portal:$(cat "$dir/portal_db_password")@postgres:5432/campus_portal"
mk portal_secret_key "$(openssl rand -hex 32)"
mk portal_admin_password "$(openssl rand -hex 12)"
echo "OK secret portal trong $dir/ (khong in gia tri)."
