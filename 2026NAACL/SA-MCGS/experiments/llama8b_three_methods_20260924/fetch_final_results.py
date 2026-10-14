#!/usr/bin/env python3
"""Fetch completed scientific results without changing the cluster output."""
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
CODE = r'''
import hashlib,io,json,pathlib,sys,tarfile,time
root=pathlib.Path('/aifs4su/hansirui_3rd/chenlong/llama8b_20260924')
out=root/'results/llama80_three_methods'
status=json.loads((root/'runs/395069/status.json').read_text())
summary=json.loads((out/'summary.json').read_text())
assert status['status']=='complete' and summary['verification_passed'] and summary['terminal_results']==240
files=sorted((out/'results').glob('*.json'))
assert len(files)==240
files += [out/n for n in ('summary.json','case_metrics.csv','frozen_protocol.json','case_plan.json')]
manifest={'job_id':'395069','fetched_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'remote_output':str(out),'files':{}}
payload=io.BytesIO()
with tarfile.open(fileobj=payload,mode='w:gz') as archive:
    for path in files:
        assert path.resolve()==path and path.is_file()
        data=path.read_bytes();name=str(path.relative_to(out))
        manifest['files'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
        entry=tarfile.TarInfo(name);entry.size=len(data);entry.mode=0o600
        archive.addfile(entry,io.BytesIO(data))
    data=(json.dumps(manifest,indent=2)+'\n').encode()
    entry=tarfile.TarInfo('download_manifest.json');entry.size=len(data);entry.mode=0o600
    archive.addfile(entry,io.BytesIO(data))
sys.stdout.buffer.write(payload.getvalue())
'''

def main():
    reply = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
        '-o', 'ConnectTimeout=15', 'Group3_slogin', '/usr/bin/python3 -B -c ' + shlex.quote(CODE)],
        capture_output=True, timeout=120)
    if reply.returncode:
        raise SystemExit(reply.stderr.decode(errors='replace'))
    destination = HERE / 'downloaded_final'
    with tarfile.open(fileobj=io.BytesIO(reply.stdout), mode='r:gz') as archive:
        contents = {}
        for entry in archive.getmembers():
            relative = Path(entry.name)
            if not entry.isfile() or relative.is_absolute() or '..' in relative.parts or entry.name in contents:
                raise RuntimeError('Unexpected archive member')
            contents[entry.name] = archive.extractfile(entry).read()
        manifest = json.loads(contents.pop('download_manifest.json'))
        assert set(contents) == set(manifest['files'])
        for name, data in contents.items():
            expected = manifest['files'][name]
            assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256']
            target = destination / name
            if target.resolve() != target:
                raise RuntimeError('Symlink in local destination')
            if target.exists() and target.read_bytes() != data:
                raise RuntimeError('Existing local result differs: ' + name)
        for name, data in contents.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(data)
        (destination / 'download_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'downloaded_files':len(contents),'result_files':len(list((destination/'results').glob('*.json'))),
        'archive_bytes':len(reply.stdout),'all_sha256_verified':True,'destination':str(destination)}))

if __name__ == '__main__':
    main()
