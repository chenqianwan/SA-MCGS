#!/usr/bin/env python3
"""Pull selected deployment evidence and preserve differing local predecessors."""
from pathlib import Path
import base64, hashlib, json, subprocess, time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
REMOTE=r'''
from pathlib import Path
import base64, hashlib, json, time
r=Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
h=r/'deployment/scale48_20261012'
paths={r/n for n in ['execution_config.json','deployment/service_supervisor.py','deployment/services_staging_manifest.json','deployment/pipeline_launch_receipt.json','deployment/pipeline_status.json','deployment/service_state.json','deployment/model_provenance.json','deployment/gpu_preflight.json','execution/status.json','endpoints.json','summary.json','RESULTS_ZH.md']}
paths.update(h.glob('*.json'))
paths.update(h/n for n in ['reconcile_completed_checkpoint.py','recover_after_exit_race.py','launch_recovery_once.py','post_restart_audit.py'])
paths.update((h/'archive_before_48').rglob('*.json'))
paths.update((h/'archive_before_48').rglob('*.py'))
paths.update((h/'replay_snapshots_frozen').rglob('evidence.json'))
paths.update((r/'deployment/runtime/415747').glob('*_command.json'))
paths.update((r/'deployment/runtime/415747').glob('*_smoke.json'))
items={}; total=0
for p in sorted(paths):
    if not p.is_file(): continue
    data=p.read_bytes(); total+=len(data)
    assert len(data)<8*1024*1024 and total<40*1024*1024
    items[str(p.relative_to(r))]={'sha256':hashlib.sha256(data).hexdigest(),'data':base64.b64encode(data).decode()}
print(json.dumps({'observed_unix':time.time(),'files':items}))
'''
cmd=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','-o','ControlMaster=auto','-o','ControlPersist=600','-o','ControlPath=/tmp/codex-qwen48-20261012-%C','Group3_slogin','python3 -']
result=subprocess.run(cmd,input=REMOTE.encode(),capture_output=True,check=True,timeout=180)
bundle=json.loads(result.stdout)
backup=HERE/'local_before_sync_20261012'
for name,item in bundle['files'].items():
    relative=Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    path=ROOT/relative
    assert path.resolve().is_relative_to(ROOT.resolve())
    data=base64.b64decode(item['data'])
    assert hashlib.sha256(data).hexdigest()==item['sha256']
    if path.exists() and path.read_bytes()!=data:
        old=backup/relative
        if not old.exists():
            old.parent.mkdir(parents=True,exist_ok=True); old.write_bytes(path.read_bytes())
    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
receipt={'observed_unix':bundle['observed_unix'],'synced_unix':time.time(),'files':{k:v['sha256'] for k,v in bundle['files'].items()},'predecessors':str(backup)}
(HERE/'local_sync_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'synced_files':len(receipt['files']),'observed_unix':receipt['observed_unix']}))
