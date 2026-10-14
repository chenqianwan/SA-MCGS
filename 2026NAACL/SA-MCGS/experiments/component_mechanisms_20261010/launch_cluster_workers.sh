#!/bin/bash
set -euo pipefail
umask 077
test "${SLURM_JOB_ID:-}" = 415747
readonly STUDY_ROOT=/aifs4su/hansirui_3rd/chenlong/mcgs_law/component_mechanisms_20261010
readonly STUDY_RUNTIME=/aifs4su/hansirui/vllm-dsv4-venv
unset PYTHONPATH OPENAI_API_KEY OPENAI_BASE_URL OPENAI_API_BASE ANTHROPIC_API_KEY
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export PYTHONHASHSEED=42 TOKENIZERS_PARALLELISM=false
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export PATH="$STUDY_RUNTIME/bin:/usr/bin:/bin"
cd "$STUDY_ROOT"
exec "$STUDY_RUNTIME/bin/python3" -B cluster_supervisor.py "$@"
