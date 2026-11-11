#!/bin/bash
# Thao tac pha huy danh tinh builder rieng; dung builder ngay sau do, khong reboot.
set -euo pipefail
test "${1:-}" = --confirm-disposable-builder || { echo 'Can --confirm-disposable-builder'; exit 1; }
test "$(id -u)" = 0
test "$(cloud-id)" = openstack
test "$(cat /etc/campuslink/image-role)" = campuslink-app-v1
test ! -e /etc/campuslink/bootstrap.json
test ! -e /run/secrets/db_password
test ! -e /run/secrets/redis_servers
test ! -e /root/.docker/config.json
test -z "$(docker ps -aq)"
test -f /opt/campuslink/build-manifest.json
cloud-init clean --help | /bin/grep -q -- --machine-id
# Khong doc noi dung key/history/user-data; chi go bo duong dan tren builder rieng.
cloud-init clean --logs --machine-id
find /root /home -maxdepth 3 -type f \( -name authorized_keys -o -name .bash_history -o -name .zsh_history \) -delete
find /etc/ssh -maxdepth 1 -type f -name 'ssh_host_*' -delete
rm -rf /run/campuslink
journalctl --rotate
journalctl --vacuum-time=1s
sync
echo 'SANITIZED; dung builder roi snapshot; khong reboot truoc snapshot'
