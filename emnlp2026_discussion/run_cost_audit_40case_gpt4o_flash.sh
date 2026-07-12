#!/usr/bin/env bash
set -euo pipefail

cd /Users/chenlong/WorkSpace/MCGS_Law

PYTHON="/opt/homebrew/anaconda3/bin/python"
CASE_CSV="emnlp2026_discussion/cost_audit_40case_gpt4o_gemini_flash.csv"
GPT_OUT="emnlp2026_discussion/cost_audit_runs/clean_40case_gpt4o_b50_20260712"
FLASH_OUT="emnlp2026_discussion/cost_audit_runs/clean_40case_gemini25flash_b50_20260712"

"$PYTHON" emnlp2026_discussion/run_cost_audit_clean.py \
  --case-csv "$CASE_CSV" \
  --output-dir "$GPT_OUT" \
  --model gpt-4o \
  --budget 50 \
  --window-size 4 \
  --internal-concurrency 1 \
  --use-all-case-rows \
  --retry-errors

"$PYTHON" emnlp2026_discussion/run_cost_audit_clean.py \
  --case-csv "$CASE_CSV" \
  --output-dir "$FLASH_OUT" \
  --model gemini-2.5-flash \
  --budget 50 \
  --window-size 4 \
  --internal-concurrency 1 \
  --use-all-case-rows \
  --retry-errors
