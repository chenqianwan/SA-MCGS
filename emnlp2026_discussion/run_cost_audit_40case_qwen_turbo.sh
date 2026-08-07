#!/usr/bin/env bash
set -euo pipefail

cd /Users/chenlong/WorkSpace/MCGS_Law

PYTHON="/opt/homebrew/anaconda3/bin/python"
CASE_CSV="emnlp2026_discussion/cost_audit_40case_qwen_turbo.csv"
QWEN_OUT="emnlp2026_discussion/cost_audit_runs/clean_40case_qwenturbo_b50_20260713"

"$PYTHON" emnlp2026_discussion/run_cost_audit_clean.py \
  --case-csv "$CASE_CSV" \
  --output-dir "$QWEN_OUT" \
  --model qwen-turbo \
  --budget 50 \
  --window-size 4 \
  --internal-concurrency 1 \
  --methods sa-mcgs lea \
  --use-all-case-rows \
  --retry-errors
