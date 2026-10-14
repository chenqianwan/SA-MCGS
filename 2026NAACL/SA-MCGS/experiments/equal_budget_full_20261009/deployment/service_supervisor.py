#!/usr/bin/env python3
"""Own eight local BF16 vLLM replicas inside existing Slurm allocation 415747.

No experiment calls, shared-environment changes, downloads, or job cancellation.
Only process groups started by this supervisor are terminated on shutdown.
"""
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_full_20261009')
PERSONAL = Path('/aifs4su/hansirui_3rd/chenlong')
RUNTIME = Path('/aifs4su/hansirui/vllm-dsv4-venv')
JOB = '415747'
MODEL_CACHE = Path('/tmp/chenlong_mcgs_415747/models')
MODELS = {
    'llama': dict(alias='llama-3.1-8b-instruct', repository='meta-llama/Llama-3.1-8B-Instruct',
        revision='0e9e39f249a16976918f6564b8830bc894c89659',
        path=str(PERSONAL/'llama8b_20260924/models/llama-3.1-8b-instruct'),
        marker=str(PERSONAL/'llama8b_20260924/model_download_complete.json'),
        official=str(PERSONAL/'llama8b_20260924/official_model_metadata.json'),
        trust_remote_code=False, chat_template_kwargs={}, max_num_seqs=16),
    'kimi': dict(alias='kimi-vl-a3b-instruct', repository='moonshotai/Kimi-VL-A3B-Instruct',
        revision='398eede0903cd983a2bfa0cc634e9ac1d843f375',
        path=str(PERSONAL/'kq35_20260924/models/kimi'),
        marker=str(PERSONAL/'kq35_20260924/prep/kimi_complete.json'),
        official=str(PERSONAL/'kq35_20260924/deployment_audit/kimi_official.json'),
        trust_remote_code=True, chat_template_kwargs={}, max_num_seqs=32),
    'qwen35': dict(alias='qwen3.5-9b', repository='Qwen/Qwen3.5-9B',
        revision='c202236235762e1c871ad0ccb60c8ee5ba337b9a',
        path=str(PERSONAL/'kq35_20260924/models/qwen35'),
        marker=str(PERSONAL/'kq35_20260924/prep/qwen35_complete.json'),
        official=str(PERSONAL/'kq35_20260924/deployment_audit/qwen35_official.json'),
        trust_remote_code=False, chat_template_kwargs={'enable_thinking': False}, max_num_seqs=32),
}
ORDER = [('llama', 0), ('kimi', 0), ('qwen35', 0), ('llama', 1),
         ('kimi', 1), ('qwen35', 1), ('llama', 2), ('kimi', 2)]
for _key, _cfg in MODELS.items():
    _cfg['original_path'] = _cfg['path']
    _cfg['path'] = str(MODEL_CACHE/_key)
    _cfg['marker'] = str(ROOT/'deployment/model_prep'/f'{_key}_complete.json')
STOP = False


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def read(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model(key):
    cfg = MODELS[key]
    folder = Path(cfg['path'])
    marker = read(cfg['marker'])
    official = read(cfg['official'])
    if (marker.get('verified') is not True or marker.get('state') != 'complete'
            or marker.get('repository') != cfg['repository']
            or marker.get('revision') != cfg['revision']
            or official.get('id') != cfg['repository'] or official.get('sha') != cfg['revision']
            or Path(marker.get('model_path', '')).resolve() != folder):
        raise RuntimeError(f'{key}: pinned checkpoint identity mismatch')
    expected = {item['rfilename']: item for item in official['siblings']
                if '/' not in item['rfilename'] and item['rfilename'] != '.gitattributes'}
    files = {}
    for item in marker['files']:
        file = Path(item['path'])
        if file.is_absolute():
            file = file.relative_to(folder)
        if file.is_absolute() or '..' in file.parts or len(file.parts) != 1:
            raise RuntimeError(f'{key}: unsafe marker entry')
        path = folder / file
        if path.resolve() != path or path.name in files:
            raise RuntimeError(f'{key}: redirected or duplicate checkpoint file')
        actual = sha(path)
        size = path.stat().st_size
        if actual != item['sha256'] or size != item['size']:
            raise RuntimeError(f'{key}: checkpoint changed: {file}')
        meta = expected.get(file.name)
        if meta and (size != meta['size'] or (meta.get('lfs') and actual != meta['lfs']['sha256'])):
            raise RuntimeError(f'{key}: official checkpoint mismatch: {file}')
        if meta and not meta.get('lfs'):
            content = path.read_bytes()
            blob = hashlib.sha1(f'blob {len(content)}\0'.encode() + content).hexdigest()
            if blob != meta['blobId']:
                raise RuntimeError(f'{key}: official source/config mismatch: {file}')
        files[file.name] = {'sha256': actual, 'bytes': size}
    if not set(expected).issubset(files):
        raise RuntimeError(f'{key}: missing checkpoint files')
    config = read(folder / 'config.json')
    if config.get('quantization_config'):
        raise RuntimeError(f'{key}: expected original unquantized checkpoint')
    return dict(repository=cfg['repository'], revision=cfg['revision'], path=str(folder),
                marker_sha256=sha(cfg['marker']), official_sha256=sha(cfg['official']),
                dtype='bfloat16', quantization=None, files=files, verified_at=now())


def command(replica):
    cfg = MODELS[replica['model_key']]
    cmd = [str(RUNTIME/'bin/python3'), '-B', '-m', 'vllm.entrypoints.openai.api_server',
           '--model', cfg['path'], '--served-model-name', cfg['alias'], '--host', '127.0.0.1',
           '--port', str(replica['port']), '--dtype', 'bfloat16', '--tensor-parallel-size', '1',
           '--max-model-len', '131072', '--max-num-seqs', str(cfg['max_num_seqs']),
           '--gpu-memory-utilization', '0.85', '--enable-chunked-prefill',
           '--max-num-batched-tokens', '8192', '--generation-config', 'vllm',
           '--override-generation-config', '{"top_k":-1,"top_p":1.0,"repetition_penalty":1.0}',
           '--enforce-eager', '--no-async-scheduling']
    if replica['model_key'] in ('kimi', 'qwen35'):
        cmd.append('--language-model-only')
    if cfg['trust_remote_code']:
        cmd.append('--trust-remote-code')
    if cfg['chat_template_kwargs']:
        cmd += ['--default-chat-template-kwargs', json.dumps(cfg['chat_template_kwargs'])]
    return cmd


def environment(run, replica):
    # Keep all writable caches per replica; shared runtime and weights stay read-only.
    base = run / replica['id']
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = os.environ.copy()
    for name in ('PYTHONPATH', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY',
                 'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
        env.pop(name, None)
    env.update(CUDA_VISIBLE_DEVICES=replica['gpu'], OMP_NUM_THREADS='4',
        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHON_DOTENV_DISABLED='1',
        PYTHONHASHSEED='42', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        HF_HUB_DISABLE_TELEMETRY='1', FLASHINFER_NO_DOWNLOAD='1', VLLM_NO_USAGE_STATS='1',
        VLLM_DO_NOT_TRACK='1', DO_NOT_TRACK='1', VLLM_ENABLE_V1_MULTIPROCESSING='0',
        VLLM_RPC_TIMEOUT='1800000', VLLM_ENGINE_ITERATION_TIMEOUT_S='1800',
        CUDA_HOME='/cm/shared/apps/cuda-12.8', CUDA_PATH='/cm/shared/apps/cuda-12.8',
        CUDA_DEVICE_ORDER='PCI_BUS_ID', LD_LIBRARY_PATH='/cm/shared/apps/cuda-12.8/lib64',
        PATH=f'{RUNTIME}/bin:/cm/shared/apps/cuda-12.8/bin:/usr/bin:/bin')
    # A short private /tmp path avoids AF_UNIX path-length failures in vLLM.
    short = Path('/tmp') / f'cl_eq_{JOB}_{replica["id"]}'
    if short.exists() and (short.is_symlink() or short.stat().st_uid != os.getuid()):
        raise RuntimeError('Unsafe per-replica temporary directory')
    short.mkdir(mode=0o700, exist_ok=True)
    cache = base / 'cache'
    paths = {'TMPDIR': short, 'TMP': short, 'TEMP': short,
        'XDG_CACHE_HOME': cache, 'XDG_CONFIG_HOME': base/'config',
        'HF_HOME': cache/'huggingface', 'HF_HUB_CACHE': cache/'huggingface/hub',
        'HUGGINGFACE_HUB_CACHE': cache/'huggingface/hub', 'HF_MODULES_CACHE': cache/'huggingface/modules',
        'TIKTOKEN_CACHE_DIR': cache/'tiktoken', 'TORCH_HOME': cache/'torch',
        'TORCHINDUCTOR_CACHE_DIR': cache/'inductor', 'TRITON_CACHE_DIR': cache/'triton',
        'NUMBA_CACHE_DIR': cache/'numba', 'VLLM_CACHE_ROOT': cache/'vllm',
        'VLLM_CONFIG_ROOT': base/'config/vllm', 'CUDA_CACHE_PATH': cache/'cuda',
        'FLASHINFER_WORKSPACE_BASE': cache/'flashinfer', 'TORCH_EXTENSIONS_DIR': cache/'torch_extensions',
        'TVM_FFI_CACHE_DIR': cache/'tvm-ffi'}
    for name, path in paths.items():
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        env[name] = str(path)
    return env


def healthy(replica):
    try:
        with urlopen(replica['base_url'] + '/models', timeout=3) as response:
            data = json.load(response)
        return [item.get('id') for item in data.get('data', [])] == [replica['alias']]
    except (OSError, ValueError):
        return False


def smoke(replica):
    body = {'model': replica['alias'], 'messages': [{'role': 'user', 'content': 'Reply with OK.'}],
            'max_tokens': 8, 'temperature': 0, 'seed': 20261009}
    if MODELS[replica['model_key']]['chat_template_kwargs']:
        body['chat_template_kwargs'] = MODELS[replica['model_key']]['chat_template_kwargs']
    request = Request(replica['base_url']+'/chat/completions', data=json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=180) as response:
        result = json.load(response)
    content = result['choices'][0]['message'].get('content')
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f'{replica["id"]}: empty synthetic smoke response')
    return {'request': body, 'response': result, 'scientific_experiment': False, 'at': now()}


def cleanup(children):
    # Groups are remembered only for Popen(start_new_session=True) performed here.
    active = [proc for proc in children.values() if proc.poll() is None]
    for proc in children.values():
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    end = time.monotonic() + 20
    while any(proc.poll() is None for proc in active) and time.monotonic() < end:
        time.sleep(.2)
    for proc in children.values():
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    if args.root.resolve() != ROOT:
        raise RuntimeError('Unexpected deployment root')
    if args.plan:
        print(json.dumps({'models': MODELS, 'order': ORDER, 'job_id': JOB}, indent=2))
        return 0
    if os.environ.get('SLURM_JOB_ID') != JOB or os.getuid() != 1083:
        raise RuntimeError('This supervisor requires the authorized allocation and account')
    visible = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
    if len(visible) != 8 or len(set(visible)) != 8 or any(not item for item in visible):
        raise RuntimeError('Expected exactly eight distinct Slurm-visible GPU identifiers')
    root = args.root
    dep = root/'deployment'
    run = dep/'runtime'/JOB
    run.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (dep/'supervisor.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (dep/'service_state.json').exists():
        raise RuntimeError('Prior service state exists; reconcile before another launch')
    children = {}
    state = dict(started_at=now(), hostname=socket.gethostname(), job_id=JOB,
                 step_id=os.environ.get('SLURM_STEP_ID'), pid=os.getpid(), status='verifying',
                 auto_restart=False, external_api_cost_usd=0, scientific_calls=0, replicas=[])
    def status(**updates):
        state.update(updates, updated_at=now())
        write(dep/'service_state.json', state)
        print(json.dumps({'status': state['status'], 'at': now(), **updates}), flush=True)
    def stop(signum, frame):
        global STOP
        STOP = True
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGUSR1):
        signal.signal(signum, stop)
    try:
        status()
        proof = {key: verify_model(key) for key in MODELS}
        versions = {key: importlib.metadata.version(key) for key in ('vllm', 'torch', 'transformers', 'tiktoken')}
        expected_versions = {'vllm': '0.20.0+cu129', 'torch': '2.11.0+cu128',
                             'transformers': '5.6.2', 'tiktoken': '0.12.0'}
        if versions != expected_versions:
            raise RuntimeError('Shared runtime differs from the previously verified versions')
        write(dep/'model_provenance.json', {'models': proof, 'versions': versions,
             'source_hashes': {p.name: sha(p) for p in dep.iterdir() if p.suffix in ('.py', '.sh')},
             'verified_at': now()})
        import torch
        if torch.cuda.device_count() != 8:
            raise RuntimeError('CUDA does not expose all eight assigned GPUs')
        gpu_proof = []
        for index in range(8):
            props = torch.cuda.get_device_properties(index)
            free, total = torch.cuda.mem_get_info(index)
            if 'H800' not in props.name or total < 75 * 1024**3 or free < .9*total:
                raise RuntimeError(f'GPU {index}: unexpected hardware or pre-existing memory use')
            gpu_proof.append(dict(index=index, visible_id=visible[index], name=props.name,
                                  free_bytes=free, total_bytes=total))
        write(dep/'gpu_preflight.json', gpu_proof)
        replicas = []
        for index, (key, number) in enumerate(ORDER):
            replicas.append(dict(id=f'{key}-{number}', gpu=visible[index], port=19081+index,
                model_key=key, replica_index=number, alias=MODELS[key]['alias'],
                base_url=f'http://127.0.0.1:{19081+index}/v1', status='planned'))
        state['replicas'] = replicas
        for batch in (replicas[:3], replicas[3:]):
            for replica in batch:
                if STOP:
                    raise InterruptedError('Deployment stopped')
                with socket.socket() as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('127.0.0.1', replica['port']))
                cmd = command(replica)
                write(run/(replica['id']+'_command.json'), {'argv': cmd, 'gpu': replica['gpu']})
                with (run/(replica['id']+'.log')).open('ab', buffering=0) as log:
                    proc = subprocess.Popen(cmd, cwd=root, env=environment(run, replica),
                        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                children[replica['id']] = proc
                replica.update(pid=proc.pid, status='starting')
                status(status='starting_services')
            deadline = time.monotonic()+2400
            while not all(replica['status'] == 'healthy' for replica in batch):
                if STOP:
                    raise InterruptedError('Deployment stopped during startup')
                for replica in batch:
                    if children[replica['id']].poll() is not None:
                        raise RuntimeError(f'{replica["id"]}: server exited during startup')
                    if replica['status'] != 'healthy' and healthy(replica):
                        write(run/(replica['id']+'_smoke.json'), smoke(replica))
                        replica.update(status='healthy', healthy_at=now())
                        status(status='starting_services')
                if time.monotonic() > deadline:
                    raise TimeoutError('Service startup exceeded forty minutes')
                time.sleep(3)
        status(status='verifying_smoke_token_counts')
        # This child only tokenizes the already recorded synthetic requests.
        with (run/'smoke_token_verification.log').open('ab', buffering=0) as log:
            audit = subprocess.Popen([str(RUNTIME/'bin/python3'), '-B', str(dep/'verify_smoke_tokens.py')],
                cwd=root, env=environment(run, replicas[0]), stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
        children['offline_token_audit'] = audit
        if audit.wait(timeout=300) != 0:
            raise RuntimeError('Deployment smoke tokenizer/usage verification failed; endpoints withheld')
        models = {key: {'alias': cfg['alias'], 'base_urls': [r['base_url'] for r in replicas if r['model_key']==key],
                   'tokenizer_path': cfg['path'], 'chat_template_kwargs': cfg['chat_template_kwargs'],
                   'trust_remote_code': cfg['trust_remote_code'], 'model_revision': cfg['revision'],
                   'max_model_len': 131072} for key, cfg in MODELS.items()}
        write(root/'endpoints.json', dict(job_id=JOB, hostname=socket.gethostname(), models=models,
                                        replicas=replicas, ready_at=now()))
        status(status='ready')
        failures = {replica['id']: 0 for replica in replicas}
        while not STOP:
            for replica in replicas:
                if children[replica['id']].poll() is not None:
                    raise RuntimeError(f'{replica["id"]}: server exited')
                failures[replica['id']] = 0 if healthy(replica) else failures[replica['id']]+1
                if failures[replica['id']] >= 3:
                    raise RuntimeError(f'{replica["id"]}: three failed health checks')
            status(status='ready', health_failures=failures)
            for _ in range(30):
                if STOP:
                    break
                time.sleep(1)
        status(status='stopped', reason='Supervisor received termination signal')
        return 0
    except BaseException as exc:
        status(status='failed', error_type=type(exc).__name__, reason=str(exc))
        return 1
    finally:
        cleanup(children)
        lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
