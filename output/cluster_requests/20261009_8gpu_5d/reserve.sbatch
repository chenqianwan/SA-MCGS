#!/bin/bash
#SBATCH --job-name=chenlong_mcgs_8g_1009
#SBATCH --partition=llm
#SBATCH --qos=llm
#SBATCH --account=hansirui
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=128
#SBATCH --gres=gpu:8
#SBATCH --mem=1000G
#SBATCH --time=5-00:00:00
#SBATCH --chdir=/aifs4su/hansirui_3rd/chenlong/mcgs_law/allocations/20261009_8gpu_5d
#SBATCH --output=/aifs4su/hansirui_3rd/chenlong/mcgs_law/allocations/20261009_8gpu_5d/slurm-%j.out
#SBATCH --error=/aifs4su/hansirui_3rd/chenlong/mcgs_law/allocations/20261009_8gpu_5d/slurm-%j.err
#SBATCH --export=NONE

set -euo pipefail
umask 077
export PATH=/cm/shared/apps/slurm/current/bin:/usr/bin:/bin
export SLURM_CONF=/cm/shared/apps/slurm/var/etc/slurm/slurm.conf
export SLURM_EXPORT_ENV=ALL

# Keep the user-requested allocation available for later workload steps.
/usr/bin/python3 -B - <<'PY'
import datetime, json, os, pathlib, socket
record = {
    'job_id': os.environ['SLURM_JOB_ID'],
    'hostname': socket.gethostname(),
    'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'slurm': {key: os.environ.get(key) for key in (
        'SLURM_JOB_NODELIST', 'SLURM_JOB_GPUS', 'CUDA_VISIBLE_DEVICES',
        'SLURM_CPUS_PER_TASK', 'SLURM_MEM_PER_NODE')},
    'purpose': 'User-requested single-node 8-GPU allocation for 5 days',
}
path = pathlib.Path('allocation-' + record['job_id'] + '.json')
with path.open('x') as f:
    json.dump(record, f, indent=2)
    f.write('\n')
print(json.dumps(record), flush=True)
PY

exec /usr/bin/sleep infinity
