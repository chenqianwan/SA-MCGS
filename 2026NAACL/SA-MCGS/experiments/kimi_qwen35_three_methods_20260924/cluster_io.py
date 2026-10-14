"""Small SSH transport for this experiment's personal cluster directory."""
from pathlib import Path
import json
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
REMOTE = '/aifs4su/hansirui_3rd/chenlong/kq35_20260924'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15',
       '-o', 'ControlMaster=auto', '-o', 'ControlPersist=600', '-o', 'ControlPath=/tmp/mcgs-kq35-%C', 'Group3_slogin']

def remote(code, payload=None, timeout=120):
    result = subprocess.run([*SSH, '/usr/bin/python3 -B -c ' + shlex.quote(code)],
                            input=payload, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace') + result.stdout.decode(errors='replace'))
    return result.stdout

if __name__ == '__main__':
    code = '''import os,subprocess,json,shutil
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
out={'uid':os.getuid(),'disk':shutil.disk_usage('/aifs4su/hansirui_3rd/chenlong')._asdict()}
for name,cmd in [('nodes',['sinfo','-p','llm','-N','-h','-o','%N|%t|%G|%m|%C']),('queue',['squeue','-u','hansirui_3rd','-h','-o','%i|%j|%T|%R|%b'])]:
 cmd[0]='/cm/shared/apps/slurm/current/bin/'+cmd[0]
 p=subprocess.run(cmd,env=env,text=True,capture_output=True)
 out[name]={'code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
print(json.dumps(out))
'''
    data = json.loads(remote(code))
    (HERE/'cluster_preflight.json').write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(data,indent=2))
