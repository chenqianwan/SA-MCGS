#!/usr/bin/env python3
"""Recover pinned official bytes into this experiment's private model directory."""
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
from service_supervisor import ROOT, MODELS, JOB, now, read, write

LOCK = threading.Lock()
STATUS = {'state': 'restoring', 'started_at': now(), 'files': {}}
LAST_WRITE = 0.0
PREP = ROOT/'deployment/model_prep'
SHARED = {'llama': Path('/aifs4su/hansirui_2nd/models/meta-llama/Llama-3.1-8B-Instruct'),
          'qwen35': Path('/aifs4su/vito/models/Qwen3.5-9B')}


def progress(key, name, force=False, **changes):
    global LAST_WRITE
    with LOCK:
        row = STATUS['files'].setdefault(key+'/'+name, {})
        row.update(changes, updated_at=now())
        if force or time.monotonic()-LAST_WRITE >= 5:
            STATUS['updated_at'] = now()
            STATUS['verified_bytes'] = sum(x.get('size', 0) for x in STATUS['files'].values() if x.get('state')=='verified')
            STATUS['bytes_present'] = sum(x.get('bytes_present', 0) for x in STATUS['files'].values())
            write(PREP/'restore_status.json', STATUS)
            LAST_WRITE = time.monotonic()


def inspect(path, expected):
    if path.is_symlink() or path.stat().st_size != expected['size']:
        raise ValueError('File size or path mismatch')
    h = hashlib.sha256()
    g = hashlib.sha1(f'blob {expected["size"]}\0'.encode())
    with path.open('rb') as src:
        for data in iter(lambda: src.read(8*1024*1024), b''):
            h.update(data)
            g.update(data)
    if expected.get('lfs'):
        if h.hexdigest() != expected['lfs']['sha256']:
            raise ValueError('Official weight hash mismatch')
    elif g.hexdigest() != expected['blobId']:
        raise ValueError('Official config/source hash mismatch')
    return dict(path=expected['rfilename'], size=expected['size'], sha256=h.hexdigest(), git_blob_sha1=g.hexdigest())


def urls(key, cfg, row):
    if key == 'llama':
        mirror = read(Path('/aifs4su/hansirui_3rd/chenlong/llama8b_20260924/models/prep/modelscope_files.json'))
        entry = next(x for x in mirror['Data']['Files'] if x.get('Path') == row['rfilename'])
        if row.get('lfs') and entry['Sha256'] != row['lfs']['sha256']:
            raise RuntimeError('Previously frozen public redistribution does not match official bytes')
        return ['https://modelscope.cn/models/LLM-Research/Meta-Llama-3.1-8B-Instruct/resolve/'
                + entry['Revision']+'/'+row['rfilename']]
    return [f'https://huggingface.co/{cfg["repository"]}/resolve/{cfg["revision"]}/{row["rfilename"]}',
            f'https://modelscope.cn/models/{cfg["repository"]}/resolve/master/{row["rfilename"]}']


def parallel_tail(key, row, part, url, offset):
    """Resume large HF tails with four bounded ranges; accept only a full-file hash."""
    remaining = row['size']-offset
    width = (remaining+3)//4
    spans = [(start, min(row['size']-1, start+width-1))
             for start in range(offset, row['size'], width)]
    paths = [part.with_name(part.name+f'.range-{start}-{end}') for start, end in spans]
    received = {i: path.stat().st_size if path.exists() else 0 for i, path in enumerate(paths)}
    def fetch(index):
        start, end = spans[index]
        path = paths[index]
        if path.is_symlink() or received[index] > end-start+1:
            raise RuntimeError('Unsafe range temporary file')
        for attempt in range(1, 5):
            have = path.stat().st_size if path.exists() else 0
            if have == end-start+1:
                return
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'MCGS-Law-Pinned-Research/1.0',
                    'Range': f'bytes={start+have}-{end}'})
                with urllib.request.urlopen(req, timeout=120) as response:
                    if response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {start+have}-'):
                        raise OSError('Server did not honor bounded range')
                    with path.open('ab') as out:
                        while True:
                            data = response.read(8*1024*1024)
                            if not data:
                                break
                            if have+len(data) > end-start+1:
                                raise OSError('Server exceeded the requested byte range')
                            out.write(data)
                            have += len(data)
                            received[index] = have
                            progress(key, row['rfilename'], state='downloading_parallel',
                                bytes_present=offset+sum(received.values()), parallel_ranges=len(spans))
                if have != end-start+1:
                    raise OSError('Range download ended early')
                return
            except (OSError, urllib.error.URLError):
                if attempt == 4:
                    raise
                time.sleep(attempt*2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, range(len(spans))))
    if part.stat().st_size != offset:
        raise RuntimeError('Sequential prefix changed during bounded range recovery')
    with part.open('ab') as output:
        for path in paths:
            with path.open('rb') as source:
                for data in iter(lambda: source.read(8*1024*1024), b''):
                    output.write(data)
    return paths


def acquire(key, cfg, row):
    name = row['rfilename']
    if Path(name).name != name or name in ('.', '..'):
        raise RuntimeError('Unsafe model file name')
    dest = Path(cfg['path'])/name
    part = dest.with_name(dest.name+'.part')
    if dest.is_symlink() or part.is_symlink():
        raise RuntimeError('Unexpected symlink in private restore directory')
    progress(key, name, size=row['size'], bytes_present=part.stat().st_size if part.exists() else 0, state='queued')
    if dest.is_file():
        result = inspect(dest, row)
        progress(key, name, force=True, state='verified', bytes_present=row['size'], source='existing_verified')
        return result
    sources = [Path(cfg['original_path'])/name]
    if key in SHARED:
        sources.append(SHARED[key]/name)
    for source in sources:
        if source.is_file() and source.stat().st_size == row['size']:
            progress(key, name, force=True, state='copying', source=str(source))
            copied = 0
            with source.open('rb') as src, part.open('wb') as out:
                for data in iter(lambda: src.read(8*1024*1024), b''):
                    out.write(data)
                    copied += len(data)
                    progress(key, name, bytes_present=copied)
            try:
                result = inspect(part, row)
            except ValueError:
                part.rename(part.with_name(part.name+f'.rejected_copy.{time.time_ns()}'))
                progress(key, name, force=True, state='source_hash_mismatch', bytes_present=0)
                continue
            part.replace(dest)
            progress(key, name, force=True, state='verified', bytes_present=row['size'])
            return {**result, 'source': str(source), 'acquisition': 'read_only_source_copy'}
    sources = urls(key, cfg, row)
    for attempt in range(1, 9):
        url = sources[(attempt-1) % len(sources)]
        try:
            offset = part.stat().st_size if part.exists() else 0
            if offset == row['size']:
                result = inspect(part, row)
                part.replace(dest)
                progress(key, name, force=True, state='verified', bytes_present=row['size'])
                return {**result, 'source': url, 'acquisition': 'public_bytes_official_hash'}
            headers = {'User-Agent': 'MCGS-Law-Pinned-Research/1.0'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            progress(key, name, force=True, state='downloading', source_host=url.split('/')[2], attempt=attempt)
            if key == 'kimi' and url.startswith('https://huggingface.co/') and offset > 0 and row['size']-offset > 256*1024**2:
                ranges = parallel_tail(key, row, part, url, offset)
                result = inspect(part, row)
                part.replace(dest)
                for piece in ranges:
                    piece.unlink()
                progress(key, name, force=True, state='verified', bytes_present=row['size'])
                return {**result, 'source': url, 'acquisition': 'four_http_ranges_official_full_sha256'}
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                resumed = offset > 0 and response.status == 206
                if resumed and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                    raise RuntimeError('Unexpected range response')
                received = offset if resumed else 0
                with part.open('ab' if resumed else 'wb') as out:
                    for data in iter(lambda: response.read(8*1024*1024), b''):
                        out.write(data)
                        received += len(data)
                        progress(key, name, bytes_present=received)
            progress(key, name, force=True, state='verifying', bytes_present=received)
            result = inspect(part, row)
            part.replace(dest)
            progress(key, name, force=True, state='verified', bytes_present=row['size'])
            return {**result, 'source': url, 'acquisition': 'public_bytes_official_hash'}
        except (OSError, ValueError, urllib.error.URLError) as exc:
            progress(key, name, force=True, state='retrying', error_type=type(exc).__name__, http_status=getattr(exc, 'code', None))
            if isinstance(exc, ValueError) and part.exists():
                part.rename(part.with_name(part.name+f'.invalid.{time.time_ns()}'))
            if attempt == 8:
                raise RuntimeError(f'{key}/{name}: public download attempts exhausted') from None
            time.sleep(min(attempt*3, 15))
    raise AssertionError('unreachable')


def main():
    os.umask(0o077)
    if os.getuid() != 1083 or os.environ.get('SLURM_JOB_ID') != JOB:
        raise RuntimeError('Restore must run within the authorized allocation')
    PREP.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (PREP/'restore.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    jobs = []
    counts = {}
    completed = {key: [] for key in MODELS}
    for key in ('qwen35', 'llama', 'kimi'):
        cfg = MODELS[key]
        Path(cfg['path']).mkdir(mode=0o700, parents=True, exist_ok=True)
        meta = read(cfg['official'])
        if meta['id'] != cfg['repository'] or meta['sha'] != cfg['revision']:
            raise RuntimeError('Official metadata revision differs from the pinned checkpoint')
        rows = [row for row in meta['siblings'] if '/' not in row['rfilename'] and row['rfilename']!='.gitattributes']
        counts[key] = len(rows)
        jobs.extend((key, cfg, row) for row in rows)
    STATUS['total_bytes'] = sum(row['size'] for _, _, row in jobs)
    write(PREP/'restore_status.json', STATUS)
    # Six file workers bound aggregate public-host and filesystem pressure.
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(acquire, key, cfg, row): key for key, cfg, row in jobs}
        for future in concurrent.futures.as_completed(pending):
            key = pending[future]
            completed[key].append(future.result())
            if len(completed[key]) == counts[key]:
                cfg = MODELS[key]
                marker = dict(state='complete', verified=True, repository=cfg['repository'],
                    revision=cfg['revision'], model_path=cfg['path'], files=completed[key], completed_at=now())
                write(Path(cfg['marker']), marker)
                print(json.dumps({'model': key, 'state': 'complete', 'at': now()}), flush=True)
    with LOCK:
        STATUS.update(state='complete', completed_at=now())
        write(PREP/'restore_status.json', STATUS)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        STATUS.update(state='failed', error_type=type(exc).__name__, reason=str(exc), updated_at=now())
        write(PREP/'restore_status.json', STATUS)
        raise
