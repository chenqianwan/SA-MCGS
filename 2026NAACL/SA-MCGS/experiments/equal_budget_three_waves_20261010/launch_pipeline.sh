#!/bin/bash
# Run only inside the existing authorized allocation; do not allocate a new job.
set -euo pipefail
umask 077
test "${SLURM_JOB_ID:-}" = 415747
test "$(id -u)" = 1083
readonly PIPELINE_ROOT=/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_three_waves_20261010
readonly PIPELINE_RUNTIME=/aifs4su/hansirui/vllm-dsv4-venv
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export PYTHONHASHSEED=42 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export SLURM_EXPORT_ENV=ALL
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
export PATH="$PIPELINE_RUNTIME/bin:/usr/bin:/bin"
cd "$PIPELINE_ROOT"
exec "$PIPELINE_RUNTIME/bin/python3" -B pipeline_supervisor.py
