#!/usr/bin/env python3
"""Restore the original pinned public Qwen72 AWQ checkpoint; no inference."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys

DEPLOY = Path(__file__).resolve().parent
MODEL_ROOT = Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20261012')
MODEL = MODEL_ROOT / 'model'
REPO = 'Qwen/Qwen2.5-72B-Instruct-AWQ'
REVISION = '698703eae6604af048a3d2f509995dc302088217'
METADATA_SHA256 = '8b97f046d6a87d6807c86e1b3ab62ffbc5421e2694e83ad58c118cad222e2a58'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, value):
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    descriptor = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    os.umask(0o077)
    if os.getuid() != 1083 or os.environ.get('SLURM_JOB_ID') != '415747':
        raise RuntimeError('Unexpected account or allocation')
    if socket.gethostname() != 'dgx-061':
        raise RuntimeError('Unexpected node')
    with (DEPLOY / 'restore_run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw = (DEPLOY / 'official_model_metadata.json').read_bytes()
        metadata = json.loads(raw)
        if (hashlib.sha256(raw).hexdigest() != METADATA_SHA256
                or metadata['id'] != REPO or metadata['sha'] != REVISION):
            raise RuntimeError('Pinned metadata differs')
        items = metadata['siblings']
        if len(items) != 21 or sum(x['size'] for x in items) != 41607438677:
            raise RuntimeError('Unexpected model inventory')
        for item in items:
            relative = Path(item['rfilename'])
            if relative.is_absolute() or '..' in relative.parts or len(relative.parts) != 1:
                raise RuntimeError('Unsafe model filename')
        if MODEL_ROOT.exists():
            raise RuntimeError('Restore destination already exists; reconcile before retry')
        space = shutil.disk_usage(MODEL_ROOT.parent)
        if space.free < 64 * 1024**3:
            raise RuntimeError('Less than 64 GiB free shared storage')
        MODEL_ROOT.mkdir(mode=0o700)
        if MODEL_ROOT.resolve() != MODEL_ROOT or MODEL_ROOT.stat().st_uid != os.getuid():
            raise RuntimeError('Unsafe model root')
        for name in ['model', 'tmp', 'cache/huggingface', 'cache/xdg', 'config']:
            (MODEL_ROOT / name).mkdir(mode=0o700, parents=True, exist_ok=True)
        os.environ.update({
            'TMPDIR': str(MODEL_ROOT / 'tmp'),
            'XDG_CACHE_HOME': str(MODEL_ROOT / 'cache/xdg'),
            'XDG_CONFIG_HOME': str(MODEL_ROOT / 'config'),
            'HF_HOME': str(MODEL_ROOT / 'cache/huggingface'),
            'HF_HUB_CACHE': str(MODEL_ROOT / 'cache/huggingface/hub'),
            'HF_XET_CACHE': str(MODEL_ROOT / 'cache/huggingface/xet'),
            'HF_HUB_DISABLE_TELEMETRY': '1', 'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
            'HF_XET_NUM_CONCURRENT_RANGE_GETS': '4',
            'HF_HUB_DOWNLOAD_TIMEOUT': '120', 'HF_HUB_ETAG_TIMEOUT': '30',
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1',
        })
        state = dict(repository=REPO, revision=REVISION, model_path=str(MODEL),
                     official_metadata_sha256=METADATA_SHA256, started_at_utc=now(),
                     state='downloading', gpu_requested=False, inference_calls=0,
                     job_id='415747', step_id=os.environ.get('SLURM_STEP_ID'),
                     hostname=socket.gethostname(), pid=os.getpid(),
                     free_bytes_before=space.free, historical_directory_unchanged=True)
        save(DEPLOY / 'model_restore_status.json', state)
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=REPO, revision=REVISION, local_dir=str(MODEL),
                          allow_patterns=[x['rfilename'] for x in items],
                          token=False, max_workers=3)
        state['state'] = 'verifying'
        state['verification_started_at_utc'] = now()
        save(DEPLOY / 'model_restore_status.json', state)
        verified = []
        for item in items:
            path = MODEL / item['rfilename']
            size = path.stat().st_size
            if path.resolve() != path or size != item['size']:
                raise RuntimeError('Model file size or path differs')
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(16 * 1024**2), b''):
                    digest.update(block)
            sha256 = digest.hexdigest()
            if item.get('lfs'):
                if sha256 != item['lfs']['sha256']:
                    raise RuntimeError('Official LFS SHA256 differs')
                verification = 'official_lfs_sha256'
            else:
                data = path.read_bytes()
                git_hash = hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + data).hexdigest()
                if not item.get('blobId') or git_hash != item['blobId']:
                    raise RuntimeError('Official Git blob differs')
                verification = 'official_git_blob_and_recorded_sha256'
            verified.append(dict(path=item['rfilename'], size=size, sha256=sha256,
                                 verification=verification))
            state['verified_files'] = len(verified)
            state['files'] = verified
            save(DEPLOY / 'model_restore_status.json', state)
            print(json.dumps({'verified': item['rfilename'], 'bytes': size}), flush=True)
        state.update(state='complete', verified=True, completed_at_utc=now(),
                     total_bytes=sum(x['size'] for x in verified))
        save(DEPLOY / 'model_download_complete.json', state)
        save(DEPLOY / 'model_restore_status.json', state)
        save(MODEL_ROOT / 'model_download_complete.json', state)
        print(json.dumps({'model_restore': 'complete', 'verified_files': len(verified),
                          'inference_calls': 0}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Do not serialize URLs, request headers, tokens, or exception payloads.
        save(DEPLOY / 'model_restore_failure.json',
             {'at_utc': now(), 'error_type': type(exc).__name__, 'inference_calls': 0})
        print(json.dumps({'model_restore': 'failed', 'error_type': type(exc).__name__}), flush=True)
        sys.exit(1)
