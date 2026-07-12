#!/usr/bin/env bash
set -euo pipefail

cd /Users/chenlong/WorkSpace/MCGS_Law

LABEL="com.mcgs.costaudit.40case.gpt4o.flash.20260712"
PLIST="/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/cost_audit_runs/com.mcgs.costaudit.40case.gpt4o.flash.20260712.plist"
LOG="/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/cost_audit_runs/cost_audit_40case_gpt4o_flash.launch.log"

echo "== Resuming EMNLP cost audit 40-case run =="
date "+%Y-%m-%d %H:%M:%S %z"

if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
  echo "LaunchAgent already loaded; unloading first to avoid duplicate runners."
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  sleep 2
fi

echo "Resume at $(date '+%Y-%m-%d %H:%M:%S %z')" >> "$LOG"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
sleep 5

echo
echo "== LaunchAgent =="
launchctl print "gui/$(id -u)/${LABEL}" | rg -n "state|pid|last exit|runs" || true

echo
echo "== Status snapshot =="
emnlp2026_discussion/check_cost_audit_40case_status.sh | sed -n '1,80p'
