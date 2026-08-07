#!/bin/zsh
set -euo pipefail

REPO_DIR="/Users/chenlong/WorkSpace/MCGS_Law"
RUN_DIR="$REPO_DIR/emnlp2026_discussion/component_ablation_runs/stage2_dynamic_gpt4o_b60_ic4_cc4_20260711_main40"
CASE_PLAN="$REPO_DIR/emnlp2026_discussion/component_ablation_stage2_dynamic40_case_plan.csv"

cd "$REPO_DIR"
echo "--- launch agent start $(date) ---" >> "$RUN_DIR/launch_agent.log"
exec /usr/bin/caffeinate -disu /opt/homebrew/anaconda3/bin/python \
  emnlp2026_discussion/run_component_ablation_stage0.py \
  --stage stage2 \
  --case-plan "$CASE_PLAN" \
  --output-dir "$RUN_DIR" \
  --budget 60 \
  --window-size 4 \
  --case-concurrency 4 \
  --internal-concurrency 4 \
  --retry-errors
