#!/usr/bin/env bash
set -euo pipefail

cd /Users/chenlong/WorkSpace/MCGS_Law
exec /opt/homebrew/anaconda3/bin/python \
  emnlp2026_discussion/cost_audit_live_dashboard/live_status_server.py \
  --host 127.0.0.1 \
  --port "${1:-8765}"
