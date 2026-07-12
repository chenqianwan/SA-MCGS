#!/usr/bin/env bash
set -euo pipefail

cd /Users/chenlong/WorkSpace/MCGS_Law

LABEL="com.mcgs.costaudit.40case.gpt4o.flash.20260712"
PLIST="/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/cost_audit_runs/com.mcgs.costaudit.40case.gpt4o.flash.20260712.plist"

echo "== Pausing EMNLP cost audit 40-case run =="
date "+%Y-%m-%d %H:%M:%S %z"

if launchctl print "gui/$(id -u)/${LABEL}" >/tmp/cost_audit_pause.$$ 2>/dev/null; then
  rg -n "state|pid|last exit|runs" /tmp/cost_audit_pause.$$ || true
  launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
  sleep 3
else
  echo "LaunchAgent was not loaded: ${LABEL}"
fi
rm -f /tmp/cost_audit_pause.$$

echo
echo "== Remaining matching processes =="
pgrep -laf "run_cost_audit_clean.py|run_cost_audit_40case_gpt4o_flash" || true

echo
echo "== Status snapshot =="
emnlp2026_discussion/check_cost_audit_40case_status.sh | sed -n '1,80p'

echo
echo "Paused. Completed result JSON files are preserved; resume with:"
echo "  emnlp2026_discussion/resume_cost_audit_40case.sh"
