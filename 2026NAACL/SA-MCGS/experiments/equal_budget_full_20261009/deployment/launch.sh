#!/bin/bash
# Invoked only inside the already allocated, authorized eight-GPU Slurm step.
set -euo pipefail
umask 077
test "${SLURM_JOB_ID:-}" = 415747
readonly ROOT=/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_full_20261009
readonly RUNTIME=/aifs4su/hansirui/vllm-dsv4-venv
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export PYTHONHASHSEED=42 SLURM_EXPORT_ENV=ALL
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export PATH="$RUNTIME/bin:/usr/bin:/bin"
cd "$ROOT"
"$RUNTIME/bin/python3" -B "$ROOT/deployment/restore_models.py"
exec "$RUNTIME/bin/python3" -B "$ROOT/deployment/service_supervisor.py" --root "$ROOT"
