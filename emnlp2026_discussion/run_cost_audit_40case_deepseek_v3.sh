#!/usr/bin/env bash
set -euo pipefail

cd /Users/chenlong/WorkSpace/MCGS_Law

PYTHON="/opt/homebrew/anaconda3/bin/python"
CASE_CSV="emnlp2026_discussion/cost_audit_40case_deepseek_v3.csv"
DEEPSEEK_OUT="emnlp2026_discussion/cost_audit_runs/clean_40case_deepseekv3_b50_20260712"

"$PYTHON" emnlp2026_discussion/run_cost_audit_clean.py \
  --case-csv "$CASE_CSV" \
  --output-dir "$DEEPSEEK_OUT" \
  --model deepseek-v3 \
  --budget 50 \
  --window-size 4 \
  --internal-concurrency 1 \
  --use-all-case-rows \
  --retry-errors
