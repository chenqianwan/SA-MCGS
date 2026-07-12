#!/bin/zsh
set -euo pipefail

REPO_DIR="/Users/chenlong/WorkSpace/MCGS_Law"
RUN_DIR="$REPO_DIR/emnlp2026_discussion/cost_audit_runs/clean_gpt4o_b50_20260711_013007"

cd "$REPO_DIR"
echo "--- launch agent start $(date) ---" >> "$RUN_DIR/run.log"
exec /usr/bin/caffeinate -disu /opt/homebrew/anaconda3/bin/python emnlp2026_discussion/run_cost_audit_clean.py \
  --output-dir "$RUN_DIR" \
  --retry-errors
