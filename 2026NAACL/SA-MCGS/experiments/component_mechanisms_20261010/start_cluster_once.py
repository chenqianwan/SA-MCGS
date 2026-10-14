#!/usr/bin/env python3
"""Explicit single dispatch; never creates an allocation or changes model services."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from cluster_runner import ROOT, read, save, sha, digest

SLURM=Path('/cm/shared/apps/slurm/current/bin')
REMOTE=Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/component_mechanisms_20261010')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume',action='store_true',help='Continue only pending/zero-request failures; never rerun a scientific outcome')
    cli=parser.parse_args()
    os.umask(0o077)
    if ROOT!=REMOTE or os.getuid()!=1083:
        raise ValueError('Dispatch is permitted only from the staged cluster study directory')
    pre=read(ROOT/'preflight/runner_prepare.json');manifest=read(ROOT/'runtime_manifest.json')
    if pre.get('status')!='passed' or pre.get('expected_results')!=1200 or pre.get('model_calls')!=0:
        raise ValueError('Offline preflight must pass before dispatch')
    if pre['runtime_manifest_sha256']!=digest(manifest):raise ValueError('Preflight manifest mismatch')
    for name,expected in {**manifest['source_hashes'],**manifest['local_science_files'],
                          'protocol.json':manifest['protocol_sha256'],
                          'run_scope.json':manifest['scope_sha256']}.items():
        if sha(ROOT/name)!=expected:raise ValueError('Source changed after preflight: '+name)
    run=ROOT/'execution';run.mkdir(exist_ok=True)
    with (run/'start.lock').open('a+') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        receipt_path=run/'step_launch_receipt.json'
        prior=read(receipt_path) if receipt_path.exists() else None
        if prior and not cli.resume:
            print(json.dumps(prior));return 0
        if cli.resume:
            if not prior or time.time()-prior['created_unix']<120:
                raise ValueError('No safely settled previous launch to resume')
            probe=(run/'supervisor.lock').open('a+')
            fcntl.flock(probe.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            probe.close()
            if (run/'status.json').exists() and read(run/'status.json').get('status') in {'complete','complete_with_failures'}:
                raise ValueError('Completed studies are never dispatched again')
            paused=run/'paused_models.json'
            if paused.exists():
                save(run/f'paused_models_before_resume_{int(time.time())}.json',read(paused))
                save(paused,{})
        env={**os.environ,'SLURM_CONF':'/cm/shared/apps/slurm/var/etc/slurm/slurm.conf','PATH':'/usr/bin:/bin'}
        output=subprocess.run([str(SLURM/'scontrol'),'show','job','415747','--oneliner'],
                     env=env,capture_output=True,text=True,check=True,timeout=30).stdout
        fields=dict(item.split('=',1) for item in output.split() if '=' in item)
        if fields.get('JobState')!='RUNNING' or fields.get('NodeList')!='dgx-061':
            raise ValueError('The existing allocation is no longer running on dgx-061')
        service=read(ROOT.parent/'equal_budget_all80_20261009/deployment/service_state.json')
        if service.get('status')!='ready':raise ValueError('Existing model services are not ready')
        command=['/usr/bin/nohup',str(SLURM/'srun'),'--jobid=415747','--overlap','--exact',
                 '--nodes=1','--ntasks=1','--cpus-per-task=64','--gres=none',
                 '--chdir='+str(ROOT),'--export=ALL','/bin/bash',str(ROOT/'launch_cluster_workers.sh')]
        if cli.resume:command.append('--recover-infrastructure')
        if prior:save(run/f"step_launch_receipt_{int(prior['created_unix'])}.json",prior)
        receipt={'status':'starting','command':command,'created_unix':time.time(),
                 'runtime_manifest_sha256':digest(manifest),'expected_results':1200,'resume':cli.resume}
        save(receipt_path,receipt)
        with (run/'step.log').open('ab',buffering=0) as log:
            child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                   cwd=ROOT,env=env,start_new_session=True,close_fds=True)
        receipt.update(status='step_process_started',launch_pid=child.pid)
        save(receipt_path,receipt);print(json.dumps(receipt))
        return 0


if __name__=='__main__':
    raise SystemExit(main())
