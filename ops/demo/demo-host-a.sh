#!/usr/bin/env bash
# Shared wrappers: use each member's existing Linux/OpenStack identity, no new privileges.
# Locally tested; live output must still be confirmed by the owner before the presentation.
set -uo pipefail
umask 077
DEMO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ACTOR="$(id -un)"
VIP_HTTP="${VIP_HTTP:-http://172.24.4.117:8080}"
LB_ID="${LB_ID:-deb301de-fb2a-430b-8bc7-2954a3afe14a}"
APP_STACK="${APP_STACK:-campus-app}"
APP_A_UUID="${APP_A_UUID:-523d67b4-9234-4b09-b3dc-c814e6b868fc}"
APP_A_IP="${APP_A_IP:-10.20.0.195}"
ALARM_STACK_ID="${ALARM_STACK_ID:-f5b0c4cf-558b-46b2-a4e2-c28d835fc275}"
ALARM_HIGH_ID="${ALARM_HIGH_ID:-37680d7a-7c46-4cf8-a789-035c7d990219}"
ALARM_LOW_ID="${ALARM_LOW_ID:-90f9060e-af83-4bba-834c-52753144421c}"
SWIFT_URL_NOAUTH="${SWIFT_URL_NOAUTH:-http://10.11.0.10:8080/v1/AUTH_07af3a3dd4c24d1ba028efcb6d28ef84/campus-backups}"
AWS_BIN="${AWS_BIN:-$HOME/.venvs/campus-aws/bin/aws}"
VA="${VA:-vol-0875752f0e893ca17}"
VB="${VB:-vol-0b7596f11ee9655f5}"
FAILOVER_SLUG="${FAILOVER_SLUG:-tv4fix1}"
STATE_DIR="${DEMO_STATE_DIR:-$HOME/.local/state/campus-demo}"
AB_PID_FILE="$STATE_DIR/ab.pid"
AB_LOG_FILE="$STATE_DIR/ab.log"
AB_START_FILE="$STATE_DIR/ab.start"
CLI_TIMEOUT="${DEMO_CLI_TIMEOUT:-30}"
if ! command -v openstack >/dev/null 2>&1 && [ -x /opt/stack/data/venv/bin/openstack ]; then
  export PATH="/opt/stack/data/venv/bin:$PATH"
fi

banner() { printf '\n=== %s | %s ===\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; return 1; }
privileged() { [[ "$ACTOR" == ubuntu || "$ACTOR" == root ]]; }
role() {
  local allowed
  privileged && return 0
  for allowed in "$@"; do [[ "$ACTOR" == "$allowed" ]] && return 0; done
  fail "This step belongs to $* / TV1; use your own prepared part. No sudo permissions are added."
}
as_user() {
  local owner="$1"; shift
  if [[ "$ACTOR" == "$owner" ]]; then "$@"
  elif privileged; then sudo -n -u "$owner" -H -- "$@"
  else fail "Cannot use another member's identity: $owner"; fi
}
os_member() { local owner="$1"; shift; as_user "$owner" timeout "$CLI_TIMEOUT" env OS_CLOUD="campus-$owner" openstack "$@"; }
os_tv2() { os_member tv2 "$@"; }
os_tv3() { os_member tv3 "$@"; }
os_tv4() { os_member tv4 "$@"; }
os_project() {
  case "$ACTOR" in tv2|tv3|tv4) os_member "$ACTOR" "$@" ;; *) os_tv2 "$@" ;; esac
}
os_admin() {
  privileged || { fail 'This infrastructure query needs the existing TV1 session.'; return 1; }
  sudo -n -u stack -H timeout "$CLI_TIMEOUT" bash -c \
    'source /opt/stack/devstack/openrc admin admin >/dev/null 2>&1; exec openstack "$@"' _ "$@"
}
json_view() { python3 "$DEMO_DIR/demo-json.py" "$@"; }
# Octavia status show already returns JSON and has no -f option.
lb_json() { os_project loadbalancer status show "$LB_ID"; }
print_lb_members() { lb_json | json_view lb; }
get_member_status() { lb_json | json_view member "$APP_A_IP"; }
alarm_summary() { os_project alarm show "$1" -f json | json_view alarm "$2"; }
alarms_disabled() {
  local aid
  for aid in "$ALARM_HIGH_ID" "$ALARM_LOW_ID"; do
    os_project alarm show "$aid" -f json | json_view alarm-disabled || return 1
  done
}
http_code() { curl -sS --max-time 6 -o /dev/null -w '%{http_code}' "$1"; }
state_init() {
  [[ ! -L "$STATE_DIR" ]] || { fail 'State directory is a symlink'; return 1; }
  mkdir -p -- "$STATE_DIR" && chmod 700 -- "$STATE_DIR"
}
read_valid_ab_pid() {
  local pid start expected
  [[ -f "$AB_PID_FILE" && -f "$AB_START_FILE" ]] || return 1
  read -r pid < "$AB_PID_FILE"
  [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/stat" ]] || return 1
  [[ "$(cat "/proc/$pid/comm" 2>/dev/null)" == ab ]] || return 1
  [[ "$(stat -c %U "/proc/$pid" 2>/dev/null)" == "$ACTOR" ]] || return 1
  start="$(awk '{print $22}' "/proc/$pid/stat" 2>/dev/null)"
  read -r expected < "$AB_START_FILE"
  [[ "$start" == "$expected" ]] || return 1
  printf '%s' "$pid"
}

cmd_pre() {
  local rc=0 code
  banner "READ-ONLY PRECHECK | actor=$ACTOR"
  os_project server list -c Name -c Status -f table || rc=1
  print_lb_members || rc=1
  os_project alarm list -c Name -c State -c Enabled -f table || rc=1
  alarm_summary "$ALARM_HIGH_ID" cpu_high || rc=1
  alarm_summary "$ALARM_LOW_ID" cpu_low || rc=1
  code="$(http_code "$VIP_HTTP/rest/health")" || rc=1
  echo "VIP health HTTP=$code (expected 200)"
  [[ "$code" == 200 ]] || rc=1
  pgrep -x ab >/dev/null 2>&1 && { echo 'WARN: another load process exists; coordinate the session'; rc=1; }
  echo 'Also verify compute, portal health, baseline 2 members and current inventory before live changes.'
  return "$rc"
}
cmd_hm1() {
  os_admin aggregate list --long -c Name -c 'Availability Zone' -c Hosts -f table || return 1
  os_admin network show campus-net -c name -c status -c mtu -f table || return 1
  os_admin server list --all-projects --long -c Name -c Status -c 'Availability Zone' -c Host -f table
}
cmd_hm2() {
  os_admin floating ip list -c 'Floating IP Address' -c 'Fixed IP Address' -c Status -f table || return 1
  os_tv2 security group rule list --ingress campus-db-sg -c Direction -c 'IP Protocol' -c 'Port Range' -c 'Remote Security Group' -f table
}
cmd_hm34() (
  local latest tempdir sha_saved sha_local code
  banner 'TV3 | CINDER, PRIVATE SWIFT, FULL SHA256'
  os_tv3 volume list -c Name -c Status -c Size -f table || exit 1
  code="$(http_code "$SWIFT_URL_NOAUTH")" || exit 1
  echo "Swift without token: HTTP=$code (expected 401)"
  [[ "$code" == 401 ]] || exit 1
  latest="$(os_tv3 object list campus-backups --prefix db/shlink- -f value -c Name | grep '\.dump$' | sort | tail -n 1)" || exit 1
  [[ -n "$latest" ]] || { fail 'No dump listed'; exit 1; }
  tempdir="$(as_user tv3 mktemp -d /tmp/campus-demo-backup.XXXXXX)" || exit 1
  [[ "$tempdir" == /tmp/campus-demo-backup.* ]] || exit 1
  trap 'as_user tv3 rm -f -- "$tempdir/dump" "$tempdir/hash"; as_user tv3 rmdir -- "$tempdir"' EXIT
  os_tv3 object save --file "$tempdir/dump" campus-backups "$latest" || exit 1
  os_tv3 object save --file "$tempdir/hash" campus-backups "${latest}.sha256" || exit 1
  sha_saved="$(as_user tv3 head -n 1 "$tempdir/hash" | awk '{print $1}')" || exit 1
  sha_local="$(as_user tv3 sha256sum "$tempdir/dump" | awk '{print $1}')" || exit 1
  [[ "$sha_saved" =~ ^[0-9a-fA-F]{64}$ ]] || { fail 'Invalid stored SHA256'; exit 1; }
  echo "Object: $latest"
  echo "Saved SHA256: $sha_saved"
  echo "Local SHA256: $sha_local"
  [[ "${sha_saved,,}" == "$sha_local" ]] || { fail 'Checksum mismatch'; exit 1; }
  echo 'PASS: full SHA256 matches; this is not a restore test.'
)
cmd_hm5() {
  local out rc
  banner 'TV1 | IAM DRY-RUN; NO VM CREATE'
  "$AWS_BIN" configure list 2>&1 | sed -E 's/[0-9]{12}/XXXXXXXXXXXX/g' || return 1
  out="$("$AWS_BIN" ec2 create-snapshot --region us-east-1 --volume-id "$VA" \
    --tag-specifications 'ResourceType=snapshot,Tags=[{Key=Project,Value=CampusLink}]' --dry-run 2>&1)"; rc=$?
  printf '%s\n' "$out" | sed -E 's/[0-9]{12}/XXXXXXXXXXXX/g'
  [[ "$rc" != 0 && "$out" == *DryRunOperation* ]] || return 1
  out="$("$AWS_BIN" ec2 create-snapshot --region us-east-1 --volume-id "$VB" \
    --tag-specifications 'ResourceType=snapshot,Tags=[{Key=Project,Value=CampusLink}]' --dry-run 2>&1)"; rc=$?
  printf '%s\n' "$out" | sed -E 's/[0-9]{12}/XXXXXXXXXXXX/g'
  [[ "$rc" != 0 && "$out" == *UnauthorizedOperation* ]] || return 1
  os_tv4 server list -c Name -c Status -f table || return 1
  echo 'Reader create-denial: show existing RBAC evidence; this wrapper never attempts VM creation.'
}
cmd_hm7() {
  os_project metric measures show -r "$APP_A_UUID" cpu --granularity 60 --aggregation rate:mean -f table | tail -n 6 || return 1
  alarm_summary "$ALARM_HIGH_ID" cpu_high || return 1
  alarm_summary "$ALARM_LOW_ID" cpu_low || return 1
  os_project alarm-history show "$ALARM_HIGH_ID" -f json | json_view history 5 || return 1
  os_project alarm-history show "$ALARM_LOW_ID" -f json | json_view history 5
}
cmd_watch() {
  local interval="${1:-10}"
  [[ "$interval" =~ ^[0-9]+$ && "$interval" -ge 1 && "$interval" -le 60 ]] || return 1
  while true; do
    banner 'AUTOSCALING | Ctrl+C exits monitoring only'
    os_project alarm list -c Name -c State -c Enabled -f table || return 1
    os_project stack event list "$APP_STACK" --limit 6 -f table || return 1
    print_lb_members || return 1
    sleep "$interval"
  done
}
cmd_alarm_on() {
  local file="${1:-}"
  [[ -n "$file" ]] || { fail 'Use alarm-on <private-env-file already confirmed by TV2>'; return 1; }
  as_user tv2 test -r "$file" || return 1
  [[ "$(as_user tv2 stat -c %a "$file")" == 600 ]] || { fail 'Private env must have mode 600'; return 1; }
  os_tv2 stack update --existing -e "$file" --wait "$ALARM_STACK_ID" || return 1
  alarm_summary "$ALARM_HIGH_ID" cpu_high && alarm_summary "$ALARM_LOW_ID" cpu_low
}
cmd_alarm_off() {
  os_tv2 stack update --existing --parameter evaluation_enabled=false --parameter actions_enabled=false \
    --parameter high_action= --parameter low_action= --wait "$ALARM_STACK_ID" || return 1
  alarms_disabled || { fail 'Could not confirm both alarms disabled with no actions'; return 1; }
  echo 'PASS: both alarms disabled and actions empty.'
}
cmd_load_start() {
  local slug="${1:-}" duration="${2:-420}" probe pid
  [[ "$slug" =~ ^[a-zA-Z0-9_-]+$ && "$slug" != tv4fix1 ]] || { fail 'Use a fresh slug (letters/digits/_/-), not tv4fix1'; return 1; }
  [[ "$duration" =~ ^[0-9]+$ && "$duration" -ge 1 && "$duration" -le 600 ]] || return 1
  command -v ab >/dev/null || return 1
  pgrep -x ab >/dev/null 2>&1 && { fail 'Another ab process exists; coordinate before starting load'; return 1; }
  state_init || return 1
  probe="$(http_code "$VIP_HTTP/$slug")" || return 1
  [[ "$probe" == 302 ]] || { fail "Slug probe HTTP=$probe, expected 302"; return 1; }
  nohup ab -k -c 64 -t "$duration" -s 10 "$VIP_HTTP/$slug" > "$AB_LOG_FILE" 2>&1 < /dev/null &
  pid=$!
  printf '%s\n' "$pid" > "$AB_PID_FILE"
  sleep 1
  [[ -r "/proc/$pid/stat" ]] || { fail 'ab exited early; inspect your private log'; return 1; }
  awk '{print $22}' "/proc/$pid/stat" > "$AB_START_FILE"
  read_valid_ab_pid >/dev/null || return 1
  echo "STARTED: ab on Host A | actor=$ACTOR | PID=$pid | slug=$slug | duration=${duration}s"
}
cmd_load_stop() {
  local pid
  if pid="$(read_valid_ab_pid)"; then
    kill -INT "$pid" || return 1
    sleep 2
    if read_valid_ab_pid >/dev/null; then
      kill -TERM "$pid" || return 1
      sleep 1
      read_valid_ab_pid >/dev/null && { fail 'ab still running; PID retained for follow-up'; return 1; }
    fi
  else
    echo 'No matching ab process owned by this account. Never stops another member process.'
  fi
  rm -f -- "$AB_PID_FILE" "$AB_START_FILE"
  if [[ -s "$AB_LOG_FILE" ]]; then
    grep -E 'Complete requests|Failed requests|Non-2xx|Requests per second|95%' "$AB_LOG_FILE" || true
  fi
  echo "Log kept: $AB_LOG_FILE"
}
cmd_fail_stop() {
  local online state n
  alarms_disabled || { fail 'Both alarms must be confirmed disabled/actions empty'; return 1; }
  online="$(lb_json | json_view online-count)" || return 1
  state="$(get_member_status)" || return 1
  [[ "$online" -ge 2 && "$state" == ONLINE ]] || { fail 'Need App A ONLINE and at least 2 ONLINE members'; return 1; }
  os_tv2 server stop "$APP_A_UUID" || return 1
  for n in {1..20}; do
    sleep 2
    state="$(get_member_status)" || { fail 'Member status unavailable; restore App A with fail-start'; return 1; }
    echo "App A: $state"
    if [[ "$state" == ERROR ]]; then
      [[ "$(http_code "$VIP_HTTP/$FAILOVER_SLUG")" == 302 ]] || return 1
      return 0
    fi
  done
  fail 'App A did not reach ERROR within polling window; restore with fail-start'
}
cmd_fail_start() {
  local n state
  os_tv2 server start "$APP_A_UUID" || return 1
  for n in {1..20}; do
    sleep 5
    state="$(get_member_status)" || return 1
    echo "App A: $state"
    [[ "$state" == ONLINE ]] && return 0
  done
  fail 'App A did not become ONLINE within polling window'
}
cmd_cleanup() {
  banner 'CHECK ONLY: no automatic alarm/VM/scale changes; logs retained'
  print_lb_members || return 1
  alarms_disabled || { fail 'Alarms not confirmed disabled'; return 1; }
  [[ "$(get_member_status)" == ONLINE ]] || return 1
  [[ "$(lb_json | json_view online-count)" == 2 ]] || { fail 'Baseline is not 2 ONLINE members'; return 1; }
  pgrep -x ab >/dev/null 2>&1 && { fail 'ab is still running'; return 1; }
  [[ "$(http_code "$VIP_HTTP/rest/health")" == 200 ]] || return 1
  echo 'PASS: core baseline checked. Check portal/laptop, keepalive and handover separately.'
}
usage() {
  cat <<'EOF'
bash /opt/campuslink-demo/demo-host-a.sh <command> [args]
TV1 ubuntu: hm1 hm2 hm5 keepalive; existing sudo can run member parts.
TV2: alarm-on <private-env> | alarm-off | load-start <fresh-slug> [seconds<=600]
     load-stop | watch [interval] | hm7 | fail-stop | fail-start
TV3: hm34 (own project volume/Swift; no sudo needed)
Members: pre | lb | cleanup (own OpenStack identity; API permissions still apply)
Do not overlap load/failover sessions. Chot kich ban phan minh truoc khi tu thu.
load-start and load-stop must use the SAME Linux account; logs remain private.
EOF
}
main() {
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    help|-h|--help) usage ;;
    hm1|hm2|hm5) role tv1 || return 1; "cmd_$cmd" "$@" ;;
    hm34) role tv3 || return 1; cmd_hm34 ;;
    keepalive) privileged || return 1; campus-keepalive "${1:-180}" ;;
    alarm-on|alarm-off|load-start|load-stop|fail-stop|fail-start)
      role tv2 || return 1; "cmd_${cmd//-/_}" "$@" ;;
    pre|hm7|watch|cleanup) "cmd_$cmd" "$@" ;;
    lb) print_lb_members ;;
    *) usage; return 2 ;;
  esac
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
