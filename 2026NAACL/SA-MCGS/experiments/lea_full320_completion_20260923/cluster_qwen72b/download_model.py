#!/usr/bin/env python3
"""Download a pinned public AWQ checkpoint and verify every official file."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20260924')
REPO = 'Qwen/Qwen2.5-72B-Instruct-AWQ'
REVISION = '698703eae6604af048a3d2f509995dc302088217'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def main():
    allowed = Path('/aifs4su/hansirui_3rd/chenlong')
    if ROOT.resolve(strict=True) != ROOT or ROOT.parent != allowed or os.getuid() != 1083:
        raise RuntimeError('Unexpected deployment directory or Unix account')
    os.umask(0o077)
    for name in ('model', 'download_tmp', 'cache/huggingface', 'cache/xdg', 'config'):
        p = ROOT / name
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
        if p.resolve() != p or p.stat().st_uid != os.getuid():
            raise RuntimeError('Unsafe task output directory')
    os.environ.update({
        'TMPDIR': str(ROOT / 'download_tmp'), 'TMP': str(ROOT / 'download_tmp'),
        'TEMP': str(ROOT / 'download_tmp'), 'XDG_CACHE_HOME': str(ROOT / 'cache/xdg'),
        'XDG_CONFIG_HOME': str(ROOT / 'config'), 'HF_HOME': str(ROOT / 'cache/huggingface'),
        'HF_HUB_CACHE': str(ROOT / 'cache/huggingface/hub'),
        'HF_XET_CACHE': str(ROOT / 'cache/huggingface/xet'),
        'HF_HUB_DISABLE_TELEMETRY': '1', 'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
        'HF_XET_NUM_CONCURRENT_RANGE_GETS': '4',
        'HF_HUB_DOWNLOAD_TIMEOUT': '120', 'HF_HUB_ETAG_TIMEOUT': '30',
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1',
    })
    manifest = json.loads((ROOT / 'official_model_metadata.json').read_text())
    if manifest['sha'] != REVISION or manifest['id'] != REPO:
        raise RuntimeError('Pinned checkpoint identity differs')
    files = manifest['siblings']
    for item in files:
        relative = Path(item['rfilename'])
        if relative.is_absolute() or '..' in relative.parts or len(relative.parts) != 1:
            raise RuntimeError('Unexpected checkpoint file path')
    status = {'repository': REPO, 'revision': REVISION, 'model_path': str(ROOT / 'model'),
              'started_at_utc': now(), 'state': 'downloading', 'gpu_requested': False}
    atomic(ROOT / 'download_status.json', status)
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=REPO, revision=REVISION, local_dir=str(ROOT / 'model'),
                      allow_patterns=[item['rfilename'] for item in files],
                      token=False, max_workers=3)
    status['state'] = 'verifying'
    atomic(ROOT / 'download_status.json', status)
    verified = []
    for item in files:
        p = ROOT / 'model' / item['rfilename']
        size = p.stat().st_size
        if p.resolve() != p or size != item['size']:
            raise RuntimeError('Model file size or physical path differs: ' + item['rfilename'])
        h = hashlib.sha256()
        with p.open('rb') as stream:
            for block in iter(lambda: stream.read(16 * 1024 * 1024), b''):
                h.update(block)
        sha = h.hexdigest()
        if item.get('lfs'):
            if sha != item['lfs']['sha256']:
                raise RuntimeError('Official LFS hash differs: ' + item['rfilename'])
            verification = 'official_lfs_sha256'
        else:
            blob = p.read_bytes()
            git_sha = hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + blob).hexdigest()
            if item.get('blobId') and git_sha != item['blobId']:
                raise RuntimeError('Official Git blob differs: ' + item['rfilename'])
            verification = 'official_git_blob_and_recorded_sha256'
        verified.append({'path': item['rfilename'], 'size': size, 'sha256': sha,
                         'verification': verification})
        print(json.dumps({'verified': item['rfilename'], 'size': size}), flush=True)
    result = {**status, 'state': 'complete', 'verified': True, 'files': verified,
              'completed_at_utc': now(), 'total_bytes': sum(x['size'] for x in verified)}
    atomic(ROOT / 'model_download_complete.json', result)
    atomic(ROOT / 'download_status.json', result)
    print(json.dumps({'download': 'complete', 'verified_files': len(verified),
                      'total_bytes': result['total_bytes']}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never serialize credentials or HTTP header-bearing exceptions.
        if ROOT.exists():
            atomic(ROOT / 'download_failure.json', {'at': now(), 'error_type': type(exc).__name__})
        raise
