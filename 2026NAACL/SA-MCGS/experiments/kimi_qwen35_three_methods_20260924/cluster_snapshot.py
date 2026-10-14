#!/usr/bin/env python3
"""Read this experiment's status, Slurm jobs, bounded logs, and counts."""
import json
from cluster_io import HERE,REMOTE,remote
CODE=r'''import pathlib, json, subprocess, os, time, collections
root=pathlib.Path(REMOTE)
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
out={'at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'root':str(root),'models':{}}
for key in ['kimi','qwen35']:
 m={};out['models'][key]=m
 for n in [f'receipts/{key}_prep.json',f'receipts/{key}_gpu.json',f'prep/{key}_status.json',f'status/{key}.json',f'recovery/{key}.json',f'results/{key}/summary.json']:
  p=root/n
  if p.exists():
   d=json.loads(p.read_text());d.pop('files',None);m[n]=d
 for phase in ['prep','gpu']:
  rec=m.get(f'receipts/{key}_{phase}.json')
  if not rec:continue
  jid=rec['job_id']
  r=subprocess.run(['/cm/shared/apps/slurm/current/bin/scontrol','show','job',jid,'-o'],env=env,text=True,capture_output=True)
  m[phase+'_slurm']=r.stdout or r.stderr
  if r.returncode:
   r=subprocess.run(['/cm/shared/apps/slurm/current/bin/sacct','-n','-P','-j',jid,'--format=JobID,State,ExitCode,NodeList,Elapsed'],env=env,text=True,capture_output=True);m[phase+'_sacct']=r.stdout or r.stderr
  files=list((root/'logs').glob(f'{key}-*{jid}.*'))
  if phase=='gpu':files+=list((root/'runs'/f'{key}-{jid}').glob('*.log'))
  m[phase+'_logs']={}
  for p in files:
   if p.is_file():
    with p.open('rb') as stream:
     stream.seek(max(0,p.stat().st_size-1800));m[phase+'_logs'][str(p.relative_to(root))]=stream.read().decode(errors='replace')
 m['downloaded_bytes']=sum(p.stat().st_size for p in (root/'models'/key).glob('*') if p.is_file() and '.invalid.' not in p.name)
 c=collections.Counter()
 for folder in ['results','infrastructure_failures']:
  for p in (root/'results'/key/folder).glob('*.json'):
   d=json.loads(p.read_text());c[d.get('cost_audit_method',d.get('method','unknown'))+':'+d.get('completion_status','unknown')]+=1
 m['counts']=dict(c)
print(json.dumps(out))
'''.replace('pathlib.Path(REMOTE)','pathlib.Path('+repr(REMOTE)+')')
if __name__=='__main__':
    report=json.loads(remote(CODE,timeout=90))
    (HERE/'cluster_live_status.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
