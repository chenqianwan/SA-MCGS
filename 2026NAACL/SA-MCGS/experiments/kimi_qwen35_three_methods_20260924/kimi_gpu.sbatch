#!/bin/bash
# One H800 hosts this model server and all three-method experiment workers.
#SBATCH --job-name=chenlong_kimi_three_methods
#SBATCH --partition=llm
#SBATCH --qos=llm
#SBATCH --account=hansirui
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:1
#SBATCH --exclude=dgx-127
#SBATCH --signal=B:USR1@600
#SBATCH --mem=128G
#SBATCH --time=5-00:00:00
#SBATCH --dependency=afterok:395439
#SBATCH --kill-on-invalid-dep=yes
#SBATCH --chdir=/aifs4su/hansirui_3rd/chenlong/kq35_20260924
#SBATCH --output=/aifs4su/hansirui_3rd/chenlong/kq35_20260924/logs/kimi-gpu-%j.out
#SBATCH --error=/aifs4su/hansirui_3rd/chenlong/kq35_20260924/logs/kimi-gpu-%j.err
#SBATCH --export=NONE

set -euo pipefail
umask 077
readonly SERVICE_ROOT=/aifs4su/hansirui_3rd/chenlong/kq35_20260924
readonly RUNTIME_ROOT=/aifs4su/hansirui/vllm-dsv4-venv
readonly ENV_ROOT="$SERVICE_ROOT/runtime/${SLURM_JOB_ID:?Slurm job required}"
readonly SHORT_TMP="$SERVICE_ROOT/t/$SLURM_JOB_ID"
export PATH=/usr/bin:/bin
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1 PYTHONHASHSEED=42
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
export SLURM_EXPORT_ENV=ALL

/usr/bin/python3 -B - "$SERVICE_ROOT" "$ENV_ROOT" "$SHORT_TMP" <<'PYGUARD'
import os, pathlib, sys
root, runtime, temp = map(pathlib.Path, sys.argv[1:])
allowed = pathlib.Path('/aifs4su/hansirui_3rd/chenlong')
if os.getuid() != 1083 or not os.environ['SLURM_JOB_ID'].isdigit():
    raise SystemExit('Expected hansirui_3rd and a numeric Slurm job ID.')
if os.environ.get('SLURM_JOB_NUM_NODES') != '1':
    raise SystemExit('Exactly one allocated node is required.')
if os.environ.get('SLURM_RESTART_COUNT', '0') != '0':
    raise SystemExit('Slurm requeue is not an authorized duplicate execution.')
for leaf in (root, root / 'logs', runtime, temp):
    if leaf.resolve() != leaf or allowed not in leaf.parents:
        raise SystemExit(f'Unsafe output path: {leaf}')
    for parent in (leaf, *leaf.parents):
        if (parent == allowed or allowed in parent.parents) and parent.exists():
            if not parent.is_dir() or parent.stat().st_uid != os.getuid():
                raise SystemExit(f'Unexpected output path owner/type: {parent}')
if len(os.fsencode(temp / '00000000-0000-0000-0000-000000000000')) > 107:
    raise SystemExit('Temporary directory exceeds the Unix socket path limit.')
for leaf in (runtime, temp):
    leaf.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    leaf.mkdir(mode=0o700)
for child in ('cache', 'config'):
    (runtime / child).mkdir(mode=0o700)
PYGUARD

export TMPDIR="$SHORT_TMP" TMP="$SHORT_TMP" TEMP="$SHORT_TMP"
export XDG_CACHE_HOME="$ENV_ROOT/cache" XDG_CONFIG_HOME="$ENV_ROOT/config"
export HF_HOME="$ENV_ROOT/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub" HF_MODULES_CACHE="$HF_HOME/modules"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export TIKTOKEN_CACHE_DIR="$ENV_ROOT/cache/tiktoken"
export TORCH_HOME="$ENV_ROOT/cache/torch" TORCHINDUCTOR_CACHE_DIR="$ENV_ROOT/cache/inductor"
export TRITON_CACHE_DIR="$ENV_ROOT/cache/triton" NUMBA_CACHE_DIR="$ENV_ROOT/cache/numba"
export VLLM_CACHE_ROOT="$ENV_ROOT/cache/vllm" VLLM_CONFIG_ROOT="$ENV_ROOT/config/vllm"
export CUDA_CACHE_PATH="$ENV_ROOT/cache/cuda" FLASHINFER_WORKSPACE_BASE="$ENV_ROOT/cache/flashinfer"
export TORCH_EXTENSIONS_DIR="$ENV_ROOT/cache/torch_extensions" TVM_FFI_CACHE_DIR="$ENV_ROOT/cache/tvm-ffi"
export FLASHINFER_NO_DOWNLOAD=1 VLLM_NO_USAGE_STATS=1 VLLM_DO_NOT_TRACK=1 DO_NOT_TRACK=1
export VLLM_ENABLE_V1_MULTIPROCESSING=0 VLLM_RPC_TIMEOUT=1800000 VLLM_ENGINE_ITERATION_TIMEOUT_S=1800
export CUDA_HOME=/cm/shared/apps/cuda-12.8 CUDA_PATH=/cm/shared/apps/cuda-12.8
export LD_LIBRARY_PATH="$CUDA_HOME/lib64"
export PATH="$RUNTIME_ROOT/bin:$CUDA_HOME/bin:/usr/bin:/bin"
# Slurm owns CUDA_VISIBLE_DEVICES; supervisor verifies that its allocated GPU is H800.
exec "$RUNTIME_ROOT/bin/python3" -B "$SERVICE_ROOT/supervisor.py" --root "$SERVICE_ROOT" --model kimi
