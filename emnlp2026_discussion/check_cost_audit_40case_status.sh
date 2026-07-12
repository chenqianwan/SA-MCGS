#!/usr/bin/env bash
set -euo pipefail

cd /Users/chenlong/WorkSpace/MCGS_Law

PYTHON="/opt/homebrew/anaconda3/bin/python"
LABEL="com.mcgs.costaudit.40case.gpt4o.flash.20260712"
GPT_STATUS="emnlp2026_discussion/cost_audit_runs/clean_40case_gpt4o_b50_20260712/status.json"
FLASH_STATUS="emnlp2026_discussion/cost_audit_runs/clean_40case_gemini25flash_b50_20260712/status.json"
GPT_CALLS="emnlp2026_discussion/cost_audit_runs/clean_40case_gpt4o_b50_20260712/call_logs/llm_calls.jsonl"
FLASH_CALLS="emnlp2026_discussion/cost_audit_runs/clean_40case_gemini25flash_b50_20260712/call_logs/llm_calls.jsonl"
RUN_LOG="emnlp2026_discussion/cost_audit_runs/cost_audit_40case_gpt4o_flash.launch.log"

echo "== EMNLP cost audit 40-case status =="
date "+%Y-%m-%d %H:%M:%S %z"
echo

echo "== LaunchAgent =="
if launchctl print "gui/$(id -u)/${LABEL}" >/tmp/cost_audit_launch_status.$$ 2>/dev/null; then
  rg -n "state|pid|last exit|runs" /tmp/cost_audit_launch_status.$$ || true
else
  echo "LaunchAgent not loaded: ${LABEL}"
fi
rm -f /tmp/cost_audit_launch_status.$$
echo

"$PYTHON" - <<'PY'
import json
from pathlib import Path

items = [
    ("gpt-4o", Path("emnlp2026_discussion/cost_audit_runs/clean_40case_gpt4o_b50_20260712/status.json")),
    ("gemini-2.5-flash", Path("emnlp2026_discussion/cost_audit_runs/clean_40case_gemini25flash_b50_20260712/status.json")),
]

for name, path in items:
    print(f"== {name} ==")
    if not path.exists():
        print(f"missing: {path}\n")
        continue
    status = json.loads(path.read_text(encoding="utf-8"))
    done = status.get("completed_method_cases", 0)
    total = status.get("total_method_cases", 0)
    failed = status.get("failed_method_cases", 0)
    remain = status.get("remaining_method_cases", 0)
    pct = (100 * done / total) if total else 0
    print(f"progress: {done}/{total} ({pct:.1f}%), failed/invalid: {failed}, remaining: {remain}")
    print(f"updated: {status.get('updated_at')}")
    current = status.get("current")
    if current:
        print(
            "current: "
            f"#{current.get('case_order')} {current.get('case_id')} | "
            f"{current.get('domain')} | SCC {current.get('scc_size')} | "
            f"{current.get('template')} | {current.get('method')} | "
            f"started {current.get('started_at')}"
        )
    else:
        print("current: none")
    print()
PY

echo "== Recent gpt-4o calls =="
tail -3 "$GPT_CALLS" 2>/dev/null || true
echo

echo "== Recent gemini-2.5-flash calls =="
tail -3 "$FLASH_CALLS" 2>/dev/null || true
echo

echo "== Recent launch log =="
tail -20 "$RUN_LOG" 2>/dev/null || true
