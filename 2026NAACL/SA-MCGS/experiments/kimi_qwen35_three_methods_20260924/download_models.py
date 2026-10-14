#!/usr/bin/env python3
"""Download public BF16 checkpoints, resume partial files, verify official hashes."""
import argparse
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

LOCK = threading.Lock()
def now(): return time.strftime('%Y-%m-%dT%H:%M:%S%z')
def read(p): return json.loads(p.read_text())
def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp=p.with_name('.'+p.name+f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(obj,indent=2)+'\n'); tmp.replace(p)
def inspect(p, row):
    if p.is_symlink() or p.stat().st_size != row['size']: raise ValueError('size/path mismatch '+row['rfilename'])
    h=hashlib.sha256(); g=hashlib.sha1(f"blob {row['size']}\0".encode())
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024), b''): h.update(b); g.update(b)
    if row.get('lfs'):
        if h.hexdigest()!=row['lfs']['sha256']: raise ValueError('official SHA256 mismatch '+row['rfilename'])
    elif g.hexdigest()!=row['blobId']: raise ValueError('official git blob mismatch '+row['rfilename'])
    return {'path':row['rfilename'],'size':row['size'],'sha256':h.hexdigest(),'git_blob_sha1':g.hexdigest()}

def download_one(root, key, meta, row):
    dest=root/'models'/key/row['rfilename']; part=dest.with_name(dest.name+'.part')
    if dest.is_file(): return {**inspect(dest,row),'source':'already_verified_personal_file'}
    # Mirror bytes are accepted only if identical to the pinned official HF version.
    urls=[f"https://modelscope.cn/models/{meta['id']}/resolve/master/{row['rfilename']}",
          f"https://huggingface.co/{meta['id']}/resolve/{meta['sha']}/{row['rfilename']}"]
    errors=[]
    for attempt in range(1,7):
        url=urls[(attempt-1)%len(urls)]
        try:
            if part.is_symlink(): raise RuntimeError('Unsafe partial file')
            offset=part.stat().st_size if part.exists() else 0
            if offset==row['size']:
                result=inspect(part,row); part.replace(dest)
                return {**result,'source':url,'attempt':attempt}
            headers={'User-Agent':'MCGS-Law-Pinned-Research/1.0'}
            if offset: headers['Range']=f'bytes={offset}-'
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=90) as res:
                resumed=offset>0 and res.status==206
                if resumed and not res.headers.get('Content-Range','').startswith(f'bytes {offset}-'):
                    raise RuntimeError('Unexpected range response')
                with part.open('ab' if resumed else 'wb') as f:
                    for b in iter(lambda:res.read(8*1024*1024),b''): f.write(b)
            result=inspect(part,row); part.replace(dest)
            return {**result,'source':url,'attempt':attempt}
        except (OSError,ValueError,urllib.error.URLError) as exc:
            errors.append({'attempt':attempt,'source_host':url.split('/')[2],'error_type':type(exc).__name__,
                           'http_status':getattr(exc,'code',None),'at':now()})
            with LOCK:
                with (root/'prep'/f'{key}_download_events.jsonl').open('a') as f:
                    f.write(json.dumps({'file':row['rfilename'],**errors[-1]})+'\n')
            if isinstance(exc,ValueError) and part.exists():
                # Quarantine our corrupt temporary file; never overwrite a verified file.
                part.rename(part.with_name(part.name+f'.invalid.{attempt}.{int(time.time())}'))
            if attempt<6: time.sleep(min(attempt*3,15))
    raise RuntimeError('Exhausted public download retries: '+row['rfilename'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--model',choices=['kimi','qwen35'],required=True)
    a=p.parse_args();root=a.root.resolve();key=a.model
    if os.getuid()!=1083 or str(root)!='/aifs4su/hansirui_3rd/chenlong/kq35_20260924': raise RuntimeError('Unexpected deployment account/root')
    os.umask(0o077)
    for d in [root/'prep',root/'models'/key]: d.mkdir(parents=True,exist_ok=True)
    lock=(root/'prep'/f'{key}.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
    meta=read(root/'deployment_audit'/f'{key}_official.json');cfg=read(root/'configs'/f'{key}.json')
    if meta['id']!=cfg['checkpoint_repository'] or meta['sha']!=cfg['checkpoint_revision']: raise RuntimeError('Pinned identity mismatch')
    files=[row for row in meta['siblings'] if '/' not in row['rfilename'] and row['rfilename']!='.gitattributes']
    status={'model':key,'repository':meta['id'],'revision':meta['sha'],'state':'downloading','started_at':now(),'expected_files':len(files),'total_bytes':sum(r['size'] for r in files),'verified_files':0,'files':[]}
    write(root/'prep'/f'{key}_status.json',status)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(download_one,root,key,meta,row) for row in files]
            for future in concurrent.futures.as_completed(futures):
                result=future.result();status['files'].append(result);status['verified_files']=len(status['files']);status['updated_at']=now()
                write(root/'prep'/f'{key}_status.json',status)
                print(json.dumps({'at':now(),'file':result['path'],'bytes':result['size'],'verified_files':len(status['files'])}),flush=True)
        status.update(state='complete',verified=True,completed_at=now(),model_path=str(root/'models'/key))
        write(root/'prep'/f'{key}_complete.json',status);write(root/'prep'/f'{key}_status.json',status)
    except Exception as exc:
        status.update(state='failed',error_type=type(exc).__name__,error=str(exc),updated_at=now())
        write(root/'prep'/f'{key}_status.json',status)
        raise
if __name__=='__main__': main()
