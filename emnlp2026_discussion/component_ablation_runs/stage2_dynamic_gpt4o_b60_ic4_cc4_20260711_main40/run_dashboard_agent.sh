#!/bin/zsh
set -euo pipefail

RUN_DIR="/Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/component_ablation_runs/stage2_dynamic_gpt4o_b60_ic4_cc4_20260711_main40"

echo "--- dashboard start $(date) ---" >> "$RUN_DIR/dashboard_agent.log"
exec /opt/homebrew/anaconda3/bin/python -m http.server 8765 \
  --bind 127.0.0.1 \
  --directory "$RUN_DIR"
