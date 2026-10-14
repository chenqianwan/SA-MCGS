#!/usr/bin/env python3
"""Read remote restoration progress and save local receipts; no inference."""
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
REMOTE = '/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012/deployment'
CODE = '''from pathlib import Path
import datetime,json
p=Path(%r);m=Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20261012/model')
d={n:json.loads((p/n).read_text()) for n in ['model_restore_status.json','model_restore_failure.json','model_download_complete.json'] if (p/n).exists()}
d['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
d['finished_model_bytes']=sum(f.stat().st_size for f in m.glob('*') if f.is_file())
d['model_files']=len([f for f in m.glob('*') if f.is_file()])
d['incomplete_bytes']=sum(f.stat().st_size for f in m.rglob('*.incomplete'))
print(json.dumps(d))
''' % REMOTE


if __name__ == '__main__':
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ConnectTimeout=15', 'Group3_slogin',
                             '/usr/bin/python3 -B -c ' + shlex.quote(CODE)],
                            capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise SystemExit('Read-only SSH check failed with status ' + str(result.returncode))
    data = json.loads(result.stdout)
    (HERE / 'model_restore_progress.json').write_text(json.dumps(data, indent=2) + '\n')
    state = data.get('model_restore_status.json', {})
    for name in ['model_download_complete.json', 'model_restore_failure.json']:
        if name in data:
            (HERE / name).write_text(json.dumps(data[name], indent=2) + '\n')
    print(json.dumps({'state': state.get('state'), 'observed_at_utc': data['observed_at_utc'],
                      'verified_files': state.get('verified_files', 0),
                      'model_files': data['model_files'],
                      'finished_model_bytes': data['finished_model_bytes'],
                      'incomplete_bytes': data['incomplete_bytes'],
                      'failure': data.get('model_restore_failure.json')}))
