#!/bin/bash
#SBATCH --job-name=chenlong_qwen35_prepare
#SBATCH --partition=debug
#SBATCH --qos=llm
#SBATCH --account=hansirui
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=08:00:00
#SBATCH --chdir=/aifs4su/hansirui_3rd/chenlong/kq35_20260924
#SBATCH --output=/aifs4su/hansirui_3rd/chenlong/kq35_20260924/logs/qwen35-prepare-%j.out
#SBATCH --error=/aifs4su/hansirui_3rd/chenlong/kq35_20260924/logs/qwen35-prepare-%j.err
#SBATCH --export=NONE
set -euo pipefail
umask 077
export PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1
export TMPDIR=/aifs4su/hansirui_3rd/chenlong/kq35_20260924/prep/tmp
exec /usr/bin/python3 -B /aifs4su/hansirui_3rd/chenlong/kq35_20260924/download_models.py --root /aifs4su/hansirui_3rd/chenlong/kq35_20260924 --model qwen35
