#!/usr/bin/env python3
"""Offline scope/source/runtime checks; never issues model requests."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if os.environ.get('SLURM_JOB_ID') != '415747':
        raise RuntimeError('Prepare inside the allocated node')
    manifest=json.loads((ROOT/'manifest.json').read_text())
    waves=[ROOT.parent/n for n in manifest['wave_dirs']]
    logs=ROOT/'preflight'
    logs.mkdir(exist_ok=True)
    checks=[]
    for wave in waves[1:]:
        env=os.environ.copy()
        env.update(PYTHONPATH=str(wave/'science/repo'),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONHASHSEED='42')
        commands=[['-m','unittest','test_budget_client','test_methods_full','test_runner','-q'],['runner.py','--prepare']]
        for ix,args in enumerate(commands):
            p=subprocess.run([sys.executable,'-B',*args],cwd=wave,env=env,text=True,capture_output=True)
            (logs/f'{wave.name}_check{ix}.log').write_text(p.stdout+p.stderr)
            checks.append({'wave':wave.name,'args':args,'exit_code':p.returncode})
            print(wave.name,args,'exit',p.returncode,flush=True)
            if p.returncode: raise RuntimeError(p.stdout+p.stderr)
    p=subprocess.run([sys.executable,'-B','-m','unittest','test_wave_audit','test_pipeline','-q'],cwd=ROOT,text=True,capture_output=True)
    (logs/'parent_tests.log').write_text(p.stdout+p.stderr)
    if p.returncode: raise RuntimeError(p.stdout+p.stderr)
    from pipeline_supervisor import validate
    _, replicas = validate(manifest)
    for replica in replicas:
        url=replica["base_url"]+"/models"
        if not url.startswith("http://127.0.0.1:"): raise RuntimeError("Nonlocal model service")
        with urllib.request.urlopen(url,timeout=10) as response:
            listing=json.load(response)
        if replica["alias"] not in [x["id"] for x in listing["data"]]:
            raise RuntimeError("Served model identity mismatch")
    from wave_audit import audit_model
    for model in manifest['models']:
        audit=audit_model(waves[0],model)
        (logs/f'wave1_{model}_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
        if not audit['complete']: raise RuntimeError('Wave1 audit did not pass: '+model+': '+str(audit['errors'][:2]))
    files=list(ROOT.glob('*.py'))+list(ROOT.glob('*.sh'))+[ROOT/'manifest.json']
    for wave in waves[1:]:
        prep=json.loads((wave/'preflight/runner_prepare.json').read_text())
        files.extend(wave/name for name in prep['protocol']['source_hashes'])
        files.extend(wave/name for name in ['run_scope.json','historical_sa_reference.json','endpoints.json','report_results.py','preflight/runner_prepare.json'])
    result={'status':'passed','model_calls':0,'expected_results_total':1440,'prepared_unix':time.time(),
            'checks':checks,'file_hashes':{str(p):sha(p) for p in sorted(set(files))}}
    (logs/'pipeline_prepare.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','model_calls','expected_results_total']}),flush=True)

if __name__=='__main__': main()
