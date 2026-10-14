#!/bin/bash
#SBATCH --job-name=chenlong_q72awq_prepare
#SBATCH --partition=debug
#SBATCH --qos=llm
#SBATCH --account=hansirui
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --chdir=/aifs4su/hansirui_3rd/chenlong/q72awq_20260924
#SBATCH --output=/aifs4su/hansirui_3rd/chenlong/q72awq_20260924/logs/download-%j.out
#SBATCH --error=/aifs4su/hansirui_3rd/chenlong/q72awq_20260924/logs/download-%j.err
#SBATCH --export=NONE
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
exec /aifs4su/hansirui/vllm-dsv4-venv/bin/python3 -I -B /aifs4su/hansirui_3rd/chenlong/q72awq_20260924/download_model.py
