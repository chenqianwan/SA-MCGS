#!/bin/bash
set -euo pipefail
umask 077
test "${SLURM_JOB_ID:-}" = 415747
readonly EXPERIMENT_ROOT=/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012
readonly EXPERIMENT_RUNTIME=/aifs4su/hansirui/vllm-dsv4-venv
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export PYTHONHASHSEED=42 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export PATH="$EXPERIMENT_RUNTIME/bin:/usr/bin:/bin"
cd "$EXPERIMENT_ROOT"
exec "$EXPERIMENT_RUNTIME/bin/python3" -B worker_supervisor.py
