#!/bin/bash
# One H800 hosts all 80 cases x three methods, then releases the allocation.
# 120h allocation; coordinator preserves checkpoints 10min before the limit.
#SBATCH --job-name=chenlong_llama8b_c4_resume
#SBATCH --partition=llm
#SBATCH --qos=llm
#SBATCH --account=hansirui
#SBATCH --nodes=1
#SBATCH --nodelist=dgx-100
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gres=gpu:1
#SBATCH --exclude=dgx-127
#SBATCH --signal=B:USR1@600
#SBATCH --mem=128G
#SBATCH --time=5-00:00:00
#SBATCH --chdir=/aifs4su/hansirui_3rd/chenlong/llama8b_20260924
#SBATCH --output=/aifs4su/hansirui_3rd/chenlong/llama8b_20260924/logs/experiment-%j.out
#SBATCH --error=/aifs4su/hansirui_3rd/chenlong/llama8b_20260924/logs/experiment-%j.err
#SBATCH --export=NONE

set -euo pipefail
umask 077
readonly SERVICE_ROOT=/aifs4su/hansirui_3rd/chenlong/llama8b_20260924
readonly RUNTIME_ROOT=/aifs4su/hansirui/vllm-dsv4-venv
readonly JOB_ROOT="$SERVICE_ROOT/runs/${SLURM_JOB_ID:?Slurm job required}"
readonly SHORT_TMP="$SERVICE_ROOT/t/${SLURM_JOB_ID}"
export PATH=/usr/bin:/bin
unset PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHON_DOTENV_DISABLED=1 PYTHONHASHSEED=42
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
export SLURM_EXPORT_ENV=ALL

/usr/bin/python3 -B - "$SERVICE_ROOT" "$JOB_ROOT" "$SHORT_TMP" <<'PY'
import os, pathlib, sys
root, run, temp = map(pathlib.Path, sys.argv[1:])
allowed = pathlib.Path('/aifs4su/hansirui_3rd/chenlong')
if os.getuid() != 1083 or not os.environ['SLURM_JOB_ID'].isdigit():
    raise SystemExit('Expected hansirui_3rd and a numeric Slurm job ID.')
for leaf in (root, root / 'logs', run, temp):
    if leaf.resolve() != leaf or allowed not in leaf.parents:
        raise SystemExit(f'Unsafe output path: {leaf}')
    for parent in (leaf, *leaf.parents):
        if (parent == allowed or allowed in parent.parents) and parent.exists():
            if not parent.is_dir() or parent.stat().st_uid != os.getuid():
                raise SystemExit(f'Unexpected output path owner/type: {parent}')
if len(os.fsencode(temp / '00000000-0000-0000-0000-000000000000')) > 107:
    raise SystemExit('Temporary directory exceeds the Unix socket path limit.')
for leaf in (run, temp):
    leaf.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    leaf.mkdir(mode=0o700)
for child in ('cache', 'config'):
    (run / child).mkdir(mode=0o700)
PY

export TMPDIR="$SHORT_TMP" TMP="$SHORT_TMP" TEMP="$SHORT_TMP"
export XDG_CACHE_HOME="$JOB_ROOT/cache" XDG_CONFIG_HOME="$JOB_ROOT/config"
export HF_HOME="$JOB_ROOT/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub" HUGGINGFACE_HUB_CACHE="$HF_HOME/hub" HF_MODULES_CACHE="$HF_HOME/modules"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export TORCH_HOME="$JOB_ROOT/cache/torch" TORCHINDUCTOR_CACHE_DIR="$JOB_ROOT/cache/inductor"
export TRITON_CACHE_DIR="$JOB_ROOT/cache/triton" NUMBA_CACHE_DIR="$JOB_ROOT/cache/numba"
export VLLM_CACHE_ROOT="$JOB_ROOT/cache/vllm" VLLM_CONFIG_ROOT="$JOB_ROOT/config/vllm"
export CUDA_CACHE_PATH="$JOB_ROOT/cache/cuda" FLASHINFER_WORKSPACE_BASE="$JOB_ROOT/cache/flashinfer"
export TORCH_EXTENSIONS_DIR="$JOB_ROOT/cache/torch_extensions" TVM_FFI_CACHE_DIR="$JOB_ROOT/cache/tvm-ffi"
export FLASHINFER_NO_DOWNLOAD=1 VLLM_NO_USAGE_STATS=1 VLLM_DO_NOT_TRACK=1 DO_NOT_TRACK=1
export VLLM_ENABLE_V1_MULTIPROCESSING=0 VLLM_RPC_TIMEOUT=1800000 VLLM_ENGINE_ITERATION_TIMEOUT_S=1800
export CUDA_HOME=/cm/shared/apps/cuda-12.8 CUDA_PATH=/cm/shared/apps/cuda-12.8
export LD_LIBRARY_PATH="$CUDA_HOME/lib64"
export PATH="$RUNTIME_ROOT/bin:$CUDA_HOME/bin:/usr/bin:/bin"
# Do not overwrite CUDA_VISIBLE_DEVICES. Slurm owns the allocation.
# The coordinator traps TERM/INT and terminates only its own child groups.
exec "$RUNTIME_ROOT/bin/python3" -B "$SERVICE_ROOT/concurrency4/port_reuse/run_llama_experiment.py" \
    --root "$SERVICE_ROOT" --job-root "$JOB_ROOT" --job-time-limit-seconds 432000 "$@"
