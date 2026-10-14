#!/usr/bin/env python3
"""Acquire the unchanged Llama checkpoint from a public redistribution.

All contents are checked against the pinned Meta repository. No credential is
read or sent, and the shared incomplete source is only read.
"""
from __future__ import annotations

import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

ROOT = Path('/aifs4su/hansirui_3rd/chenlong/llama8b_20260924')
MODEL = ROOT / 'models/llama-3.1-8b-instruct'
PREP = ROOT / 'models/prep'
SOURCE = Path('/aifs4su/hansirui_2nd/models/meta-llama/Llama-3.1-8B-Instruct')
REPOSITORY = 'meta-llama/Llama-3.1-8B-Instruct'
REVISION = '0e9e39f249a16976918f6564b8830bc894c89659'
LOCK = threading.Lock()
VERIFIED = []
EVENTS = []
SOURCE_AUDIT = {}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic(path, value):
    if path.parent.resolve() != path.parent or path.is_symlink():
        raise RuntimeError('Unsafe output path')
    temp = path.with_name(path.name + '.tmp')
    if temp.is_symlink():
        raise RuntimeError('Unsafe temporary output path')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def inspect_file(path, item):
    size = path.stat().st_size
    if size != item['size']:
        raise ValueError('Size mismatch: ' + item['rfilename'])
    sha256 = hashlib.sha256()
    git_sha1 = hashlib.sha1(b'blob ' + str(size).encode() + b'\0')
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            sha256.update(block)
            git_sha1.update(block)
    if item.get('lfs'):
        if sha256.hexdigest() != item['lfs']['sha256']:
            raise ValueError('LFS mismatch: ' + item['rfilename'])
        verification = 'official_lfs_sha256'
    else:
        if git_sha1.hexdigest() != item['blobId']:
            raise ValueError('Git blob mismatch: ' + item['rfilename'])
        verification = 'official_git_blob_and_recorded_sha256'
    return {'path': item['rfilename'], 'size': size,
            'sha256': sha256.hexdigest(), 'git_blob_sha1': git_sha1.hexdigest(),
            'verification': verification}


def event(kind, **fields):
    record = {'at': now(), 'event': kind, **fields}
    with LOCK:
        EVENTS.append(record)
        atomic(PREP / 'download_events.json', EVENTS)
        print(json.dumps(record), flush=True)


def acquire(item, mirror):
    name = item['rfilename']
    dest = MODEL / name
    temp = MODEL / (name + '.part')
    if dest.is_symlink() or temp.is_symlink():
        raise RuntimeError('Unsafe model file path')
    if dest.is_file():
        result = inspect_file(dest, item)
        result['acquisition'] = 'verified_existing_personal_file'
        return result
    existing = SOURCE / name
    if existing.is_file() and existing.stat().st_size == item['size']:
        try:
            source_check = SOURCE_AUDIT.get(name) or inspect_file(existing, item)
        except ValueError:
            event('shared_source_mismatch', file=name)
        else:
            with existing.open('rb') as src, temp.open('wb') as out:
                for block in iter(lambda: src.read(8 * 1024 * 1024), b''):
                    out.write(block)
            result = inspect_file(temp, item)
            temp.replace(dest)
            result['acquisition'] = 'copied_readonly_existing_shared_file'
            result['source_path'] = str(existing)
            result['source_sha256'] = source_check['sha256']
            event('shared_source_verified_and_copied', file=name, size=result['size'])
            return result
    source = mirror[name]
    url = ('https://modelscope.cn/models/LLM-Research/'
           'Meta-Llama-3.1-8B-Instruct/resolve/' + source['Revision'] + '/' + name)
    for attempt in range(1, 5):
        try:
            offset = temp.stat().st_size if temp.exists() else 0
            headers = {'User-Agent': 'LlamaPinnedCheckpointResearch/1.0'}
            if offset:
                headers['Range'] = 'bytes=' + str(offset) + '-'
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                resumed = offset > 0 and response.status == 206
                if resumed and not response.headers.get('Content-Range', '').startswith('bytes ' + str(offset) + '-'):
                    raise RuntimeError('Unexpected download content range')
                with temp.open('ab' if resumed else 'wb') as output:
                    for block in iter(lambda: response.read(8 * 1024 * 1024), b''):
                        output.write(block)
            result = inspect_file(temp, item)
            temp.replace(dest)
            result.update({'acquisition': 'public_modelscope_redistribution',
                           'source_url': url, 'source_sha256': source['Sha256']})
            event('public_file_verified', file=name, size=result['size'])
            return result
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            event('network_retry', file=name, attempt=attempt,
                  error_type=type(exc).__name__, http_status=getattr(exc, 'code', None))
            if attempt == 4 or getattr(exc, 'code', None) in (401, 403, 404):
                raise RuntimeError('Public source unavailable for ' + name) from None
            time.sleep(min(5 * attempt, 20))
    raise RuntimeError('Unreachable download state')


def main():
    os.umask(0o077)
    if ROOT.resolve(strict=True) != ROOT or os.getuid() != 1083:
        raise RuntimeError('Unexpected account or task directory')
    for path in (ROOT / 'models', MODEL, PREP):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.resolve() != path or path.stat().st_uid != os.getuid():
            raise RuntimeError('Unsafe model directory')
    official = json.loads((ROOT / 'official_model_metadata.json').read_text())
    redistribution = json.loads((PREP / 'modelscope_files.json').read_text())
    if official['id'] != REPOSITORY or official['sha'] != REVISION:
        raise RuntimeError('Unexpected official checkpoint identity')
    mirror = {x['Path']: x for x in redistribution['Data']['Files'] if x.get('Type') == 'blob'}
    files = [x for x in official['siblings'] if '/' not in x['rfilename']]
    if len([x for x in files if x['rfilename'].endswith('.safetensors')]) != 4:
        raise RuntimeError('Unexpected number of canonical weight shards')
    for item in files:
        name = item['rfilename']
        if Path(name).name != name or name in ('.', '..') or name not in mirror:
            raise RuntimeError('Unsafe or missing checkpoint file')
        if mirror[name]['Size'] != item['size']:
            raise RuntimeError('Public source size differs from pinned official file')
        if item.get('lfs') and mirror[name]['Sha256'] != item['lfs']['sha256']:
            raise RuntimeError('Public source weight differs from pinned official file')
    status = {'repository': REPOSITORY, 'revision': REVISION, 'model_path': str(MODEL),
              'started_at_utc': now(), 'state': 'downloading', 'gpu_requested': False,
              'source_repository': 'LLM-Research/Meta-Llama-3.1-8B-Instruct',
              'source_host': 'modelscope.cn', 'license_files_preserved': True,
              'official_hf_access': 'existing_token_has_no_gate_access; no further gated requests',
              'selection': 'all official top-level files; excludes duplicate original/ format'}
    atomic(ROOT / 'download_status.json', status)
    # Verify the two existing shared shards before acquiring missing content.
    for item in files:
        candidate = SOURCE / item['rfilename']
        if item.get('lfs') and candidate.is_file() and candidate.stat().st_size == item['size']:
            SOURCE_AUDIT[item['rfilename']] = inspect_file(candidate, item)
            event('existing_shared_shard_matches_official', file=item['rfilename'],
                  sha256=SOURCE_AUDIT[item['rfilename']]['sha256'])
    atomic(PREP / 'existing_shared_shard_verification.json', SOURCE_AUDIT)
    # Two concurrent files limit filesystem pressure and public-host connections.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(acquire, item, mirror) for item in files]
        for future in concurrent.futures.as_completed(futures):
            VERIFIED.append(future.result())
            atomic(ROOT / 'download_status.json', {**status, 'verified_files': len(VERIFIED)})
    VERIFIED.sort(key=lambda row: row['path'])
    marker = {**status, 'state': 'complete', 'verified': True, 'files': VERIFIED,
              'completed_at_utc': now(), 'total_bytes': sum(x['size'] for x in VERIFIED),
              'official_metadata_sha256': hashlib.sha256((ROOT / 'official_model_metadata.json').read_bytes()).hexdigest(),
              'redistribution_metadata_sha256': hashlib.sha256((PREP / 'modelscope_files.json').read_bytes()).hexdigest()}
    atomic(ROOT / 'model_download_complete.json', marker)
    atomic(ROOT / 'download_status.json', marker)
    print(json.dumps({'download': 'complete', 'verified_files': len(VERIFIED),
                      'total_bytes': marker['total_bytes']}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Persist neither tokens nor remote exception bodies.
        atomic(ROOT / 'download_failure.json', {'at': now(), 'error_type': type(exc).__name__})
        print(json.dumps({'download': 'failed', 'error_type': type(exc).__name__}), flush=True)
        raise SystemExit(1)
