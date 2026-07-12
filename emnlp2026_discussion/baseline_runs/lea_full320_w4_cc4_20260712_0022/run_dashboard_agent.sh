#!/bin/zsh
set -euo pipefail
cd /Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/baseline_runs/lea_full320_w4_cc4_20260712_0022
exec /opt/homebrew/anaconda3/bin/python -m http.server 8765 --bind 127.0.0.1
