#!/bin/zsh
set -euo pipefail
cd /Users/chenlong/WorkSpace/MCGS_Law
exec /usr/bin/caffeinate -disu /opt/homebrew/anaconda3/bin/python \
  /Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/run_lea_full_baseline.py \
  --output-dir /Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/baseline_runs/lea_available160_gpt4o_gemini_w4_cc4_20260712_0048 \
  --models gpt-4o gemini-2.5-pro \
  --case-concurrency 4 \
  --window-size 4 \
  --retry-errors
