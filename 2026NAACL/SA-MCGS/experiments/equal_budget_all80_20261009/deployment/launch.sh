#!/bin/bash
set -euo pipefail
umask 077
test "${SLURM_JOB_ID:-}" = 415747
readonly BASE=/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_all80_20261009
readonly RUNTIME=/aifs4su/hansirui/vllm-dsv4-venv
case "${1:-balanced}" in
  balanced) export MCGS_SERVICE_TOPOLOGY=balanced; readonly RUNROOT="$BASE" ;;
  original) export MCGS_SERVICE_TOPOLOGY=original; readonly RUNROOT="$BASE/deployment/rollback_original" ;;
  *) exit 64 ;;
esac
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export PYTHONHASHSEED=42 SLURM_EXPORT_ENV=ALL
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export PATH="$RUNTIME/bin:/usr/bin:/bin"
mkdir -p "$RUNROOT/deployment"
cd "$RUNROOT"
"$RUNTIME/bin/python3" -B "$BASE/deployment/retire_previous.py"
exec "$RUNTIME/bin/python3" -B "$BASE/deployment/service_supervisor.py" --root "$RUNROOT"
