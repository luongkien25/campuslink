#!/usr/bin/env bash
# add-member.sh - TV1 chay tren host A de tao user Linux rieng cho 1 thanh vien (khong sudo).
#   sudo ops/add-member.sh tv2 "ssh-ed25519 AAAA... ten@may"
# Cong 22 dang mo 0.0.0.0/0 theo ADR-07; tu freeze 06/11 nho them IP /32 cua thanh vien vao SG. Ghi ten vao
# docs/inventory.yaml (ssh.members_with_key). User Keystone tao rieng (FR-INF-18).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Chay bang sudo" >&2; exit 1; }
[ "$#" -eq 2 ] || { echo "Cach dung: $0 <user> '<public key>'" >&2; exit 2; }
u="$1"; key="$2"
case "$u" in tv2|tv3|tv4) ;; *) echo "User chi nhan tv2|tv3|tv4" >&2; exit 2;; esac
case "$key" in ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*) ;; *) echo "Khong giong public key" >&2; exit 2;; esac

id "$u" >/dev/null 2>&1 || adduser --disabled-password --gecos "CampusLink $u" "$u"
usermod -aG systemd-journal "$u"           # doc log devstack@*, khong co sudo
install -d -m 700 -o "$u" -g "$u" "/home/$u/.ssh" "/home/$u/.config/openstack"
grep -qxF "$key" "/home/$u/.ssh/authorized_keys" 2>/dev/null || echo "$key" >> "/home/$u/.ssh/authorized_keys"
chown "$u:$u" "/home/$u/.ssh/authorized_keys"; chmod 600 "/home/$u/.ssh/authorized_keys"
echo "Xong: $u. Thanh vien tu tao /home/$u/.config/openstack/clouds.yaml (chmod 600)."
