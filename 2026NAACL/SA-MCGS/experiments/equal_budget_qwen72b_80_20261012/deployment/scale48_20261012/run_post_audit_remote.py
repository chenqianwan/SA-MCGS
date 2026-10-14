from pathlib import Path
import json,os,subprocess
root=Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
here=root/'deployment/scale48_20261012'
state=json.loads((root/'execution/status.json').read_text())
assert state['status']=='running' and state['running_workers']==48, '48 workers are not ready'
env=os.environ.copy(); env['SLURM_CONF']='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf';env['SLURM_EXPORT_ENV']='ALL'
cmd=['/cm/shared/apps/slurm/current/bin/srun','--jobid=415747','--overlap','--exact','--nodes=1','--ntasks=1','--cpus-per-task=1','--gres=none','--nodelist=dgx-061','--chdir='+str(root),'--export=ALL','/usr/bin/env','CUDA_VISIBLE_DEVICES=','/aifs4su/hansirui/vllm-dsv4-venv/bin/python3','-B',str(here/'post_restart_audit.py'),'--output','post_restart_audit.json']
previous=here/'post_restart_audit.json'; initial=here/'post_restart_audit_initial.json'
if previous.exists() and not initial.exists(): initial.write_bytes(previous.read_bytes())
completed=subprocess.run(cmd,cwd=root,env=env,timeout=120)
raise SystemExit(completed.returncode)
