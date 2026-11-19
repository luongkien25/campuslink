#!/bin/bash
# CampusLink - cai backup len DB VM (FR-INF-15). TV3.
# Chay tren DB VM: sudo ./install.sh   (trong thu muc chua cac file cua app/db/backup/)
# Credential doc tu stdin neu co (id=..., secret=..., 2 dong), ghi /root/campus-backup/cred 0600; khong in ra.
#   vd tu laptop: ssh campus-a 'cat ~/campus-backup-cred' | ssh campus-db 'cd ~/backup && sudo ./install.sh --cred-stdin'
# Khong bat timer (bat bang tay sau khi chay thu 1 lan: systemctl enable --now campus-db-backup.timer).
set -euo pipefail
cd "$(dirname "$0")"
[[ $EUID == 0 ]] || { echo "can sudo"; exit 1; }

install -m 755 campus-db-backup campus-db-restore-test /usr/local/sbin/
install -m 644 campus-db-backup.service campus-db-backup.timer /etc/systemd/system/
[[ -e /etc/campus-backup.conf ]] || install -m 644 campus-backup.conf.example /etc/campus-backup.conf
install -d -m 700 /root/campus-backup
if [[ ${1:-} == --cred-stdin ]]; then
  install -m 600 /dev/stdin /root/campus-backup/cred
fi
ok=$(grep -c -E '^(id|secret)=.+' /root/campus-backup/cred 2>/dev/null || true)
systemctl daemon-reload
echo "OK da cai; cred: ${ok:-0}/2 dong hop le; timer: $(systemctl is-enabled campus-db-backup.timer 2>/dev/null || true)"
