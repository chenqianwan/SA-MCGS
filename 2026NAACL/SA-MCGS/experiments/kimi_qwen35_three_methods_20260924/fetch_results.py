#!/usr/bin/env python3
"""Download settled model results once; verify bytes and never overwrite changes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
from cluster_io import HERE,REMOTE,remote

def main():
    p=argparse.ArgumentParser();p.add_argument('--models',nargs='+',choices=['kimi','qwen35'],default=['kimi','qwen35']);a=p.parse_args()
    code=r'''import pathlib,json,hashlib,io,tarfile,sys,time
root=pathlib.Path(ROOT)
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as archive:
 for key in KEYS:
  output=root/'results'/key
  summary=json.loads((output/'summary.json').read_text())
  if summary.get('terminal_results')!=240 or not summary.get('verification_passed'):raise RuntimeError('Model not settled: '+key)
  files=[output/n for n in ['case_plan.json','frozen_protocol.json','summary.json','portable_preflight.json','tokenization_report.json'] if (output/n).exists()]
  files+=list((output/'results').glob('*.json'))+list((output/'infrastructure_failures').glob('*.json'))
  manifest={'model':key,'source':str(output),'scientific_complete':summary.get('scientific_complete'),'files':{}}
  for path in files:
   if path.resolve()!=path or not path.is_file():raise RuntimeError('Unsafe result path')
   data=path.read_bytes();name=str(path.relative_to(output))
   manifest['files'][name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
   info=tarfile.TarInfo(key+'/'+name);info.size=len(data);info.mode=0o600;archive.addfile(info,io.BytesIO(data))
  data=(json.dumps(manifest,indent=2)+'\n').encode();info=tarfile.TarInfo(key+'/download_manifest.json');info.size=len(data);info.mode=0o600;archive.addfile(info,io.BytesIO(data))
sys.stdout.buffer.write(buf.getvalue())
'''.replace('pathlib.Path(ROOT)','pathlib.Path('+repr(REMOTE)+')').replace('for key in KEYS:','for key in '+repr(a.models)+':')
    payload=remote(code,timeout=180);out=HERE/'downloaded_final';out.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        pending=[]
        for member in archive.getmembers():
            rel=Path(member.name)
            if not member.isfile() or rel.is_absolute() or '..' in rel.parts or rel.parts[0] not in a.models:raise RuntimeError('Unsafe archive member')
            path=out/rel;data=archive.extractfile(member).read()
            if path.resolve()!=path:raise RuntimeError('Symlink target')
            if path.exists() and path.read_bytes()!=data:raise RuntimeError('Refuse replacing changed local result: '+str(rel))
            pending.append((path,data))
        for path,data in pending:
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                with path.open('xb') as stream:stream.write(data)
    for key in a.models:
        manifest=json.loads((out/key/'download_manifest.json').read_text())
        for name,e in manifest['files'].items():
            content=(out/key/name).read_bytes()
            if len(content)!=e['bytes'] or hashlib.sha256(content).hexdigest()!=e['sha256']:raise RuntimeError('Downloaded SHA mismatch')
    print(json.dumps({'models':a.models,'output':str(out),'verified':True,'archive_bytes':len(payload)}))
if __name__=='__main__':main()
