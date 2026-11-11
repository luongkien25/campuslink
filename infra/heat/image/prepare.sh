#!/bin/bash
# Chi chay thu cong trong builder Nova rieng, khong chay tren EC2/laptop.
set -euo pipefail
test "${1:-}" = --confirm-openstack-builder || { echo 'Can --confirm-openstack-builder'; exit 1; }
test "$(id -u)" = 0
test "$(cloud-id)" = openstack
. /etc/os-release
test "$ID" = ubuntu && test "$VERSION_ID" = 24.04
test "$(dpkg --print-architecture)" = amd64
source_commit=${2:-}
test "${#source_commit}" = 40
[[ "$source_commit" =~ ^[a-f0-9]{40}$ ]]
repo=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
test ! -e /etc/campuslink/bootstrap.json
test ! -e /run/secrets/db_password
test ! -e /run/secrets/redis_servers
test ! -e /root/.docker/config.json
test "$(df --output=avail -B1 / | tail -1)" -ge 3000000000
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends docker.io curl python3 redis-tools ca-certificates coreutils iptables
install -d -m 0700 /etc/campuslink
install -d -m 0755 /opt/campuslink/bootstrap /etc/docker
printf '%s\n' campuslink-app-v1 > /etc/campuslink/image-role
# Khong ghi de cau hinh daemon da co: builder phai rieng va sach.
test ! -e /etc/docker/daemon.json
docker_major=$(dockerd --version | sed -E 's/.*version ([0-9]+).*/\1/')
if test "$docker_major" -ge 29; then
  printf '%s\n' '{"mtu":1400,"firewall-backend":"iptables"}' > /etc/docker/daemon.json
else
  printf '%s\n' '{"mtu":1400}' > /etc/docker/daemon.json
fi
systemctl enable --now docker
systemctl restart docker
test -z "$(docker ps -aq)"
image='shlinkio/shlink@sha256:68a722f7677008a50ccf3a9e570966bc37d7627fe6a870b86be28c5dcf9085ee'
docker pull --platform linux/amd64 "$image"
test "$(docker image inspect "$image" --format '{{.Architecture}}')" = amd64
install -m 0644 "$repo"/infra/heat/bootstrap/*.py /opt/campuslink/bootstrap/
install -m 0755 "$repo"/infra/heat/bootstrap/*.sh /opt/campuslink/bootstrap/
install -m 0644 "$repo/app/shlink.env.example" /opt/campuslink/shlink.env
install -m 0755 "$repo/app/smoke/redis-probe.sh" /opt/campuslink/redis-probe.sh
install -m 0644 "$repo"/infra/heat/bootstrap/systemd/*.service /etc/systemd/system/
install -d -m 0755 /etc/systemd/system/docker.service.d
install -m 0644 "$repo/infra/heat/bootstrap/systemd/docker.service.d/campuslink.conf" /etc/systemd/system/docker.service.d/
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/campuslink-*.service
# Chi manifest cua builder, khong phai Glance image da nghiem thu.
python3 "$repo/infra/heat/image/manifest.py" "$repo" /opt/campuslink/build-manifest.json "$source_commit"
echo 'PREPARED; chua sanitize/snapshot/kiem clone'
