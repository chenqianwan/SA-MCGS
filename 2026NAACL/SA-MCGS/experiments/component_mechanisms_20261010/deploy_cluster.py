#!/usr/bin/env python3
"""Stage this study and run offline preparation; this script never launches workers."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
HOST='Group3_slogin'
REMOTE='/aifs4su/hansirui_3rd/chenlong/mcgs_law/component_mechanisms_20261010'
RUNTIME='/aifs4su/hansirui/vllm-dsv4-venv/bin/python3'


def ssh_python(source):
    return subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST,'python3 -'],
                          input=source,text=True,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true',help='Also run remote offline validation after staging')
    cli=parser.parse_args()
    required=['cluster_runner.py','cluster_supervisor.py','cluster_status.py','start_cluster_once.py',
              'launch_cluster_workers.sh','mechanism_patches.py','concurrent_ledger.py','offline_analysis.py',
              'protocol.json','run_scope.json','test_cluster_runner.py','test_concurrent_ledger.py',
              'test_mechanism_patches.py']
    missing=[name for name in required if not (ROOT/name).is_file()]
    if missing:raise ValueError('Study is not ready to stage: '+', '.join(missing))
    # Deliberately prohibit accidental redeployment over an already-started study.
    ssh_python('import pathlib,shutil\n'
               f'p=pathlib.Path({REMOTE!r})\n'
               "if (p/'execution/step_launch_receipt.json').exists(): raise RuntimeError('Study already dispatched; staging disabled')\n"
               "p.mkdir(parents=True,exist_ok=True)\n(p/'preflight').mkdir(exist_ok=True)\n"
               "src=p.parent/'equal_budget_full_20261009/science'\n"
               "if not (p/'science').exists(): shutil.copytree(src,p/'science')\n")
    sources=[str(ROOT/name) for name in required]
    subprocess.run(['scp','-q',*sources,f'{HOST}:{REMOTE}/'],check=True)
    helpers=ROOT/'replay_helpers'
    if not helpers.is_dir():raise ValueError('Frozen offline replay helpers are required')
    subprocess.run(['scp','-qr',str(helpers),f'{HOST}:{REMOTE}/'],check=True)
    for name in ['replay_helpers_sha256.json','scope_verification.json']:
        path=ROOT/'preflight'/name
        if path.exists():subprocess.run(['scp','-q',str(path),f'{HOST}:{REMOTE}/preflight/'],check=True)
    if cli.prepare:
        command='cd '+shlex.quote(REMOTE)+' && env PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=42 PYTHON_DOTENV_DISABLED=1 '+shlex.quote(RUNTIME)+' -B cluster_runner.py --prepare'
        subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',HOST,command],check=True)
    print(json.dumps({'staged':REMOTE,'offline_prepare_requested':cli.prepare,'workers_started':False}))


if __name__=='__main__':main()
