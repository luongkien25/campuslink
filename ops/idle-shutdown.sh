#!/usr/bin/env bash
# idle-shutdown.sh - tu tat host khi khong ai dung, tranh quen tat EC2 (SRS NFR-16, O-09).
# Chay boi campus-idle-shutdown.timer moi 5 phut.
#   Host A (MODE=a): dang dung neu co phien SSH, co tien trinh dai (stack.sh, pg_dump, locust...),
#                    hoac file giu may con han. Khong dung qua IDLE_MIN phut -> poweroff.
#   Host B (MODE=b): dang dung neu co phien SSH tren B hoac A con song. A tat -> B tat theo.
# Can chay viec dai ma khong giu SSH (vd do tai tu laptop): ssh campus-a 'campus-keepalive 180'
# EC2 phai de "Shutdown behavior = Stop" (mac dinh); poweroff trong OS = Stop instance.
set -u
MODE="${MODE:-a}"
IDLE_MIN="${IDLE_MIN:-60}"
A_IP="${A_IP:-10.11.0.10}"
DIR="${DIR:-/var/tmp}"
KEEP="$DIR/campus-keepalive."           # .<user>, mtime trong tuong lai = giu may den luc do
LAST="$DIR/campus-last-active"
PROCS='stack\.sh|unstack\.sh|pg_dump|pg_restore|locust|apt-get|dpkg'
now=$(date +%s)

active=""
[ "$(who | wc -l)" -gt 0 ] && active="ssh"
if [ -z "$active" ]; then
  for k in "$KEEP"*; do
    [ -f "$k" ] && [ "$(stat -c %Y "$k")" -gt "$now" ] && active="keepalive" && break
  done
fi
if [ "$MODE" = a ]; then
  [ -z "$active" ] && pgrep -x "$PROCS" >/dev/null 2>&1 && active="process"
else
  [ -z "$active" ] && timeout 5 bash -c "</dev/tcp/$A_IP/22" 2>/dev/null && active="host-a-up"
fi
# vua boot: tinh nhu dang dung
[ -z "$active" ] && [ "$(cut -d. -f1 /proc/uptime)" -lt "${BOOT_GRACE:-1200}" ] && active="boot"

if [ -n "$active" ] || [ ! -f "$LAST" ]; then
  touch "$LAST"; exit 0
fi
idle=$(( (now - $(stat -c %Y "$LAST")) / 60 ))
[ "$MODE" = b ] && IDLE_MIN=15
if [ "$idle" -ge "$IDLE_MIN" ]; then
  logger -t campus-idle "khong ai dung ${idle} phut -> poweroff"
  ${POWEROFF:-systemctl poweroff}
fi
