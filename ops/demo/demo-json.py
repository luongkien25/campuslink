#!/usr/bin/env python3
"""Format selected OpenStack JSON fields without printing action URLs or tokens."""

import json
import sys


def members(data):
    lb = data.get("loadbalancer", data)
    return [member for listener in lb.get("listeners", [])
            for pool in listener.get("pools", []) for member in pool.get("members", [])]


def main():
    action, *args = sys.argv[1:]
    try:
        data = json.load(sys.stdin)
        if action == "lb":
            lb = data.get("loadbalancer", data)
            items = members(data)
            if not items:
                raise ValueError("no LB members")
            print("LB: %s | operating=%s" % (lb.get("name", ""), lb.get("operating_status", "UNKNOWN")))
            for item in items:
                print("  %s:%s operating=%s provisioning=%s" % (
                    item.get("address"), item.get("protocol_port"),
                    item.get("operating_status", "UNKNOWN"), item.get("provisioning_status", "UNKNOWN")))
        elif action == "member":
            found = [m for m in members(data) if m.get("address") == args[0]]
            if len(found) != 1:
                raise ValueError("member absent or ambiguous")
            state = found[0].get("operating_status")
            if not state:
                raise ValueError("missing operating status")
            print(state)
        elif action == "online-count":
            print(sum(m.get("operating_status") == "ONLINE" for m in members(data)))
        elif action in ("alarm", "alarm-disabled"):
            if not isinstance(data, dict):
                raise ValueError("invalid alarm response")
            enabled = data.get("enabled")
            acts = data.get("alarm_actions")
            if not isinstance(acts, list) or enabled not in (True, False, "True", "False", "true", "false"):
                raise ValueError("missing alarm enabled/actions")
            if action == "alarm-disabled":
                return 0 if str(enabled).lower() == "false" and not acts else 1
            print("%s state=%s enabled=%s action_count=%d" % (
                args[0], data.get("state", "UNKNOWN"), enabled, len(acts)))
        elif action == "history":
            if not isinstance(data, list):
                raise ValueError("invalid history response")
            shown = 0
            for item in sorted(data, key=lambda row: row.get("timestamp", ""), reverse=True):
                if item.get("type") != "state transition":
                    continue
                detail = item.get("detail", {})
                if isinstance(detail, str):
                    detail = json.loads(detail)
                state = detail.get("state", "UNKNOWN")
                if state not in ("ok", "alarm", "insufficient data", "UNKNOWN"):
                    state = "UNKNOWN"
                print("%s state=%s" % (item.get("timestamp", ""), state))
                shown += 1
                if shown >= int(args[0]):
                    break
            if not shown:
                print("No state transition recorded.")
        else:
            raise ValueError("unknown formatter")
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        print("FAIL: unavailable or invalid JSON; no state confirmed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
