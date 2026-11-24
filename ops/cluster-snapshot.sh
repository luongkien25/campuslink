#!/usr/bin/env bash
# cluster-snapshot.sh - chup trang thai cum OpenStack (CHI DOC) de chan doan khi debug.
#
# Chay tu may ca nhan (khong can copy script len A):
#   ssh campus-a 'OS_CLOUD=<ten-cloud> bash -s -- lb' < ops/cluster-snapshot.sh > snap.txt
# Phan: base | net | lb | heat | telemetry | storage | logs | all   (co the ghi nhieu phan)
#
# Script tu che chuoi giong mat khau/token/API key/Account ID, nhung VAN DOC LAI truoc khi dan.
# Lenh can admin (vd compute service list) se bao loi quyen voi user member/reader: binh thuong.

set -u
export CLIFF_FIT_WIDTH=1
T=40   # timeout moi lenh (giay)

if ! command -v openstack >/dev/null 2>&1 && [ -x /opt/stack/data/venv/bin/openstack ]; then
  PATH="/opt/stack/data/venv/bin:$PATH"
fi

redact() {
  sed -E \
    -e 's#(redis|rediss|postgres|postgresql|amqp|mysql\+pymysql)://[^@/ ]*@#\1://<REDACTED>@#g' \
    -e 's#([Pp][Aa][Ss][Ss][Ww]([Oo][Rr])?[Dd]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Tt][Oo][Kk][Ee][Nn]|[Aa][Pp][Ii][_-]?[Kk][Ee][Yy])("?[[:space:]]*[:=][[:space:]]*"?)[^"[:space:],]+#\1\3<REDACTED>#g' \
    -e 's#gAAAAA[A-Za-z0-9_=-]{20,}#<TOKEN>#g' \
    -e 's#\b[0-9]{12}\b#<ACCOUNT_ID>#g'
}

run() {   # run <lenh...>: in tieu de, chay co timeout, che secret
  echo "### \$ $*"
  timeout "$T" "$@" 2>&1 | redact
  echo
}

ids() {   # ids <lenh openstack list...>: in cot ID
  timeout "$T" "$@" -f value -c ID 2>/dev/null
}

s_base() {
  echo "## base"
  run date -u
  run hostname
  run uptime
  run openstack --version
  echo "OS_CLOUD=${OS_CLOUD:-<chua dat>}"; echo
  run openstack server list --long
  run openstack compute service list
  run openstack network agent list
}

s_net() {
  echo "## net"
  run openstack network list --long
  run openstack subnet list --long
  run openstack router list --long
  run openstack floating ip list --long
  run openstack port list --long
  run openstack security group list
  for sg in $(ids openstack security group list); do
    run openstack security group rule list "$sg" --long
  done
  run ip -br addr
  run ip route
}

s_lb() {
  echo "## lb"
  run openstack loadbalancer list
  for lb in $(ids openstack loadbalancer list); do
    run openstack loadbalancer status show "$lb"
  done
  run openstack loadbalancer listener list
  run openstack loadbalancer healthmonitor list
  for p in $(ids openstack loadbalancer pool list); do
    run openstack loadbalancer member list "$p"
  done
}

s_heat() {
  echo "## heat"
  run openstack stack list --nested
  for st in $(timeout "$T" openstack stack list -f value -c 'Stack Name' 2>/dev/null); do
    run openstack stack resource list --nested-depth 2 "$st"
    echo "### \$ openstack stack event list --nested-depth 2 $st | tail -n 40"
    timeout "$T" openstack stack event list --nested-depth 2 "$st" 2>&1 | tail -n 40 | redact
    echo
  done
}

s_telemetry() {
  echo "## telemetry"
  run openstack alarm list
  for a in $(timeout "$T" openstack alarm list -f value -c alarm_id 2>/dev/null); do
    run openstack alarm show "$a"
    echo "### \$ openstack alarm-history show $a | head -n 30"
    timeout "$T" openstack alarm-history show "$a" 2>&1 | head -n 30 | redact
    echo
  done
  echo "### \$ openstack metric resource list --type instance | head -n 40"
  timeout "$T" openstack metric resource list --type instance 2>&1 | head -n 40 | redact
  echo
}

s_storage() {
  echo "## storage"
  run openstack volume list --long
  run openstack volume service list
  run openstack container list
}

s_logs() {
  echo "## logs (30 phut gan nhat, muc warning tro len)"
  run systemctl --failed --no-pager
  echo "### \$ journalctl -u 'devstack@*' --since '-30 min' -p warning | tail -n 150"
  timeout "$T" journalctl -u 'devstack@*' --since '-30 min' -p warning --no-pager 2>&1 | tail -n 150 | redact
  echo
}

[ "$#" -eq 0 ] && set -- base
for part in "$@"; do
  case "$part" in
    base|net|lb|heat|telemetry|storage|logs) "s_$part" ;;
    all) s_base; s_net; s_lb; s_heat; s_telemetry; s_storage; s_logs ;;
    *) echo "Phan khong hop le: $part (base|net|lb|heat|telemetry|storage|logs|all)" >&2; exit 2 ;;
  esac
done
