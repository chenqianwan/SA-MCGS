#!/bin/bash
#SBATCH --job-name=chenlong_llama8b_prepare
#SBATCH --partition=debug
#SBATCH --qos=llm
#SBATCH --account=hansirui
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --chdir=/aifs4su/hansirui_3rd/chenlong/llama8b_20260924/models/prep
#SBATCH --output=/aifs4su/hansirui_3rd/chenlong/llama8b_20260924/models/prep/logs/download-%j.out
#SBATCH --error=/aifs4su/hansirui_3rd/chenlong/llama8b_20260924/models/prep/logs/download-%j.err
#SBATCH --export=NONE
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
export TMPDIR=/aifs4su/hansirui_3rd/chenlong/llama8b_20260924/models/prep/tmp
exec /aifs4su/hansirui/vllm-dsv4-venv/bin/python3 -I -B /aifs4su/hansirui_3rd/chenlong/llama8b_20260924/models/prep/download_model.py
