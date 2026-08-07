#!/bin/zsh
set -euo pipefail
cd /Users/chenlong/WorkSpace/MCGS_Law/emnlp2026_discussion/supplement_report_dashboard
exec /opt/homebrew/anaconda3/bin/python -m http.server 8765 --bind 127.0.0.1
