#!/usr/bin/env python3
"""Own four TP2 pinned Qwen72 AWQ services in allocation 415747; never retire others."""
from __future__ import annotations
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
import uuid
from urllib.request import Request, urlopen

DEPLOY = Path(__file__).resolve().parent
ROOT = DEPLOY.parent
AUTHORIZED_ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
RUNTIME = Path('/aifs4su/hansirui/vllm-dsv4-venv')
MODEL_PATH = Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20261012/model')
MODEL_ALIAS = 'qwen2.5-72b-instruct'
MODEL_REPO = 'Qwen/Qwen2.5-72B-Instruct-AWQ'
MODEL_REVISION = '698703eae6604af048a3d2f509995dc302088217'
METADATA_SHA256 = '8b97f046d6a87d6807c86e1b3ab62ffbc5421e2694e83ad58c118cad222e2a58'
JOB = '415747'
NODE = 'dgx-061'
MAX_MODEL_LEN = 131072
TP_SIZE = 2
REPLICA_COUNT = 4
HF_OVERRIDES = {'rope_parameters': {'rope_type': 'yarn', 'factor': 4.0,
                'original_max_position_embeddings': 32768, 'rope_theta': 1000000.0}}
OWNER_TOKEN = uuid.uuid4().hex
STOP = False


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def read(path):
    return json.loads(Path(path).read_text())


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with temporary.open('w') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(16 * 1024**2), b''):
            digest.update(chunk)
    return digest.hexdigest()


def process_identity(pid):
    process = Path('/proc')/str(pid)
    stat = (process/'stat').read_text()
    tail = stat[stat.rfind(')') + 2:].split()
    return {'pid': pid, 'start_ticks': tail[19], 'process_group': int(tail[2]),
            'uid': process.stat().st_uid, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def verify_model():
    marker_path = DEPLOY/'model_download_complete.json'
    official_path = DEPLOY/'official_model_metadata.json'
    marker, official = read(marker_path), read(official_path)
    if (sha(official_path) != METADATA_SHA256 or marker.get('verified') is not True
            or marker.get('state') != 'complete' or marker.get('repository') != MODEL_REPO
            or marker.get('revision') != MODEL_REVISION or official.get('id') != MODEL_REPO
            or official.get('sha') != MODEL_REVISION
            or Path(marker.get('model_path', '')).resolve() != MODEL_PATH
            or MODEL_PATH.resolve() != MODEL_PATH):
        raise RuntimeError('Pinned Qwen checkpoint identity or download completion mismatch')
    expected = {item['rfilename']: item for item in official['siblings']}
    files = {}
    for item in marker['files']:
        name = item['path']
        if Path(name).name != name or name in files:
            raise RuntimeError('Unsafe or duplicate checkpoint marker entry')
        path = MODEL_PATH/name
        meta = expected.get(name)
        if not meta or path.resolve() != path or path.stat().st_size != item['size'] or item['size'] != meta['size']:
            raise RuntimeError('Checkpoint file identity or size mismatch: '+name)
        actual = sha(path)
        if actual != item['sha256']:
            raise RuntimeError('Checkpoint changed since restore: '+name)
        if meta.get('lfs'):
            if actual != meta['lfs']['sha256']:
                raise RuntimeError('Official checkpoint LFS hash mismatch: '+name)
        else:
            data = path.read_bytes()
            blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if blob != meta['blobId']:
                raise RuntimeError('Official checkpoint source/config mismatch: '+name)
        files[name] = {'sha256': actual, 'bytes': item['size']}
    if set(files) != set(expected):
        raise RuntimeError('Checkpoint file coverage differs from pinned official inventory')
    cfg = read(MODEL_PATH/'config.json')
    quantization = cfg.get('quantization_config', {})
    if cfg.get('model_type') != 'qwen2' or quantization.get('quant_method') != 'awq' or quantization.get('bits') != 4:
        raise RuntimeError('Expected the original 4-bit AWQ Qwen2 checkpoint')
    return {'repository': MODEL_REPO, 'revision': MODEL_REVISION, 'path': str(MODEL_PATH),
            'marker_sha256': sha(marker_path), 'official_sha256': sha(official_path),
            'dtype': 'float16', 'quantization': 'awq', 'files': files, 'verified_at': now()}


def command(replica):
    return [str(RUNTIME/'bin/python3'), '-B', '-m', 'vllm.entrypoints.openai.api_server',
            '--model', str(MODEL_PATH), '--served-model-name', MODEL_ALIAS,
            '--host', '127.0.0.1', '--port', str(replica['port']),
            '--dtype', 'float16', '--quantization', 'awq', '--tensor-parallel-size', str(TP_SIZE),
            '--hf-overrides', json.dumps(HF_OVERRIDES, separators=(',', ':')),
            '--max-model-len', str(MAX_MODEL_LEN), '--max-num-seqs', '12',
            '--gpu-memory-utilization', '0.90', '--enable-chunked-prefill',
            '--max-num-batched-tokens', '8192', '--generation-config', 'vllm',
            '--override-generation-config', '{"top_k":-1,"top_p":1.0,"repetition_penalty":1.0}',
            '--enforce-eager', '--no-async-scheduling']


def environment(run, replica):
    base = run/replica['id']
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    env = os.environ.copy()
    for name in ('PYTHONPATH', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY',
                 'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
        env.pop(name, None)
    env.update(CUDA_VISIBLE_DEVICES=replica['gpu'], OMP_NUM_THREADS='4',
        MCGS_Q72_SERVICE_OWNER=OWNER_TOKEN, VLLM_WORKER_MULTIPROC_METHOD='spawn',
        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHON_DOTENV_DISABLED='1',
        PYTHONHASHSEED='42', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
        HF_HUB_DISABLE_TELEMETRY='1', HF_HUB_DISABLE_IMPLICIT_TOKEN='1', FLASHINFER_NO_DOWNLOAD='1',
        VLLM_NO_USAGE_STATS='1', VLLM_DO_NOT_TRACK='1', DO_NOT_TRACK='1',
        VLLM_ENABLE_V1_MULTIPROCESSING='0', VLLM_RPC_TIMEOUT='1800000',
        VLLM_ENGINE_ITERATION_TIMEOUT_S='1800', CUDA_HOME='/cm/shared/apps/cuda-12.8',
        CUDA_PATH='/cm/shared/apps/cuda-12.8', CUDA_DEVICE_ORDER='PCI_BUS_ID',
        LD_LIBRARY_PATH='/cm/shared/apps/cuda-12.8/lib64',
        PATH=f'{RUNTIME}/bin:/cm/shared/apps/cuda-12.8/bin:/usr/bin:/bin')
    short = Path('/tmp')/f'clq72_{JOB}_{replica["id"]}'
    if short.exists() and (short.is_symlink() or short.stat().st_uid != os.getuid()):
        raise RuntimeError('Unsafe per-replica temporary directory')
    cache = base/'cache'
    paths = {'TMPDIR': short, 'TMP': short, 'TEMP': short, 'XDG_CACHE_HOME': cache,
        'XDG_CONFIG_HOME': base/'config', 'HF_HOME': cache/'huggingface',
        'HF_HUB_CACHE': cache/'huggingface/hub', 'HF_MODULES_CACHE': cache/'huggingface/modules',
        'TORCH_HOME': cache/'torch', 'TORCHINDUCTOR_CACHE_DIR': cache/'inductor',
        'TRITON_CACHE_DIR': cache/'triton', 'VLLM_CACHE_ROOT': cache/'vllm',
        'VLLM_CONFIG_ROOT': base/'config/vllm', 'CUDA_CACHE_PATH': cache/'cuda',
        'FLASHINFER_WORKSPACE_BASE': cache/'flashinfer', 'TORCH_EXTENSIONS_DIR': cache/'torch_extensions',
        'TVM_FFI_CACHE_DIR': cache/'tvm-ffi'}
    for name, path in paths.items():
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        env[name] = str(path)
    return env


def healthy(replica):
    try:
        with urlopen(replica['base_url']+'/models', timeout=3) as response:
            data = json.load(response)
        return [item.get('id') for item in data.get('data', [])] == [MODEL_ALIAS]
    except (OSError, ValueError):
        return False


def smoke(replica, tokenizer):
    body = {'model': MODEL_ALIAS, 'messages': [{'role': 'user', 'content': 'Reply with OK.'}],
            'max_tokens': 8, 'temperature': 0, 'seed': 42}
    request = Request(replica['base_url']+'/chat/completions', data=json.dumps(body).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=180) as response:
        result = json.load(response)
    content = result['choices'][0]['message'].get('content')
    ids = tokenizer.apply_chat_template(body['messages'], tokenize=True, add_generation_prompt=True)
    if isinstance(ids, dict) or hasattr(ids, 'keys'):
        ids = ids['input_ids']
    expected = len(ids)
    usage = result.get('usage', {})
    if (not isinstance(content, str) or not content.strip() or result.get('model') != MODEL_ALIAS
            or usage.get('prompt_tokens') != expected
            or type(usage.get('completion_tokens')) is not int or usage['completion_tokens'] < 1
            or usage['completion_tokens'] > body['max_tokens']
            or usage.get('total_tokens') != expected + usage['completion_tokens']):
        raise RuntimeError(replica['id']+': synthetic smoke response/tokenizer usage mismatch')
    return {'request': body, 'response': result, 'expected_prompt_tokens': expected,
            'prompt_token_match': True, 'scientific_experiment': False, 'at': now()}


def owned_group_alive(group_id):
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            identity = process_identity(int(process.name))
            if identity['process_group'] != group_id:
                continue
            env = (process/'environ').read_bytes().split(b'\0')
            if ('MCGS_Q72_SERVICE_OWNER='+OWNER_TOKEN).encode() in env:
                return True
        except (OSError, ValueError, IndexError):
            continue
    return False


def cleanup(children):
    # Only groups from our own Popen objects with an inherited private owner token.
    def signal_owned(sig):
        for proc in children.values():
            if owned_group_alive(proc.pid):
                try:
                    os.killpg(proc.pid, sig)
                except ProcessLookupError:
                    pass
    signal_owned(signal.SIGTERM)
    end = time.monotonic() + 45
    while any(owned_group_alive(proc.pid) for proc in children.values()) and time.monotonic() < end:
        time.sleep(.2)
    signal_owned(signal.SIGKILL)
    for proc in children.values():
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true')
    args = parser.parse_args()
    if args.plan:
        replicas = [{'id': f'qwen25-{i}', 'gpu': ','.join(str(g) for g in range(2*i, 2*i+2)), 'port': 19271+i} for i in range(REPLICA_COUNT)]
        print(json.dumps({'job_id': JOB, 'node': NODE, 'model': MODEL_REPO,
                          'revision': MODEL_REVISION, 'replicas': [{**r, 'argv': command(r)} for r in replicas],
                          'tensor_parallel_size': TP_SIZE, 'max_model_len': MAX_MODEL_LEN, 'hf_overrides': HF_OVERRIDES,
                          'manages_preexisting_services': False}, indent=2))
        return 0
    if (ROOT != AUTHORIZED_ROOT or os.environ.get('SLURM_JOB_ID') != JOB
            or os.getuid() != 1083 or socket.gethostname() != NODE):
        raise RuntimeError('Requires the exact authorized root, allocation, account and node')
    visible = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
    if len(visible) != 8 or len(set(visible)) != 8 or any(not gpu for gpu in visible):
        raise RuntimeError('Expected eight distinct Slurm-visible GPUs')
    os.umask(0o077)
    run = DEPLOY/'runtime'/JOB
    run.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (DEPLOY/'service_supervisor.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (DEPLOY/'service_state.json').exists() or (ROOT/'endpoints.json').exists():
        raise RuntimeError('Prior service state/endpoints exist; reconcile instead of duplicating services')
    children = {}
    endpoint_published = False
    state = {'started_at': now(), 'hostname': socket.gethostname(), 'job_id': JOB,
             'step_id': os.environ.get('SLURM_STEP_ID'), 'pid': os.getpid(),
             'process_identity': process_identity(os.getpid()), 'status': 'verifying',
             'auto_restart': False, 'scientific_calls': 0, 'synthetic_smoke_calls': 0,
             'manages_preexisting_services': False, 'replicas': []}

    def status(**updates):
        state.update(updates, updated_at=now())
        write(DEPLOY/'service_state.json', state)
        print(json.dumps({'status': state['status'], 'at': now(), **updates}), flush=True)

    def stop(signum, frame):
        global STOP
        STOP = True

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGUSR1):
        signal.signal(signum, stop)
    try:
        status()
        versions = {key: importlib.metadata.version(key) for key in ('vllm', 'torch', 'transformers', 'tiktoken')}
        expected = {'vllm': '0.20.0+cu129', 'torch': '2.11.0+cu128', 'transformers': '5.6.2', 'tiktoken': '0.12.0'}
        if versions != expected:
            raise RuntimeError('Shared runtime differs from pinned versions')
        proof = verify_model()
        from vllm.transformers_utils.config import get_config
        effective = get_config(str(MODEL_PATH), trust_remote_code=False, hf_overrides_kw=HF_OVERRIDES)
        rope = effective.rope_parameters
        if any(rope.get(key) != value for key, value in HF_OVERRIDES['rope_parameters'].items()):
            raise RuntimeError('Pinned vLLM runtime did not apply the expected official YaRN parameters')
        proof['in_memory_hf_overrides'] = HF_OVERRIDES
        proof['checkpoint_files_modified'] = False
        write(DEPLOY/'model_provenance.json', {'model': proof, 'versions': versions,
              'source_hashes': {p.name: sha(p) for p in DEPLOY.glob('*.py')}, 'verified_at': now()})
        from context_preflight import audit
        context = audit(MODEL_PATH, MAX_MODEL_LEN, ROOT/'preflight/context_validation_deployed.json')
        if context['status'] != 'passed':
            raise RuntimeError('Frozen case prompts exceed context; no truncation or model startup allowed')
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH), local_files_only=True, trust_remote_code=False)
        import torch
        if torch.cuda.device_count() != 8:
            raise RuntimeError('CUDA does not expose all eight assigned GPUs')
        gpu_proof = []
        for index in range(8):
            props = torch.cuda.get_device_properties(index)
            free, total = torch.cuda.mem_get_info(index)
            if 'H800' not in props.name or total < 75*1024**3 or free < .95*total:
                raise RuntimeError(f'GPU {index}: unexpected hardware or pre-existing GPU use; no other process will be stopped')
            gpu_proof.append({'index': index, 'visible_id': visible[index], 'name': props.name,
                              'free_bytes': free, 'total_bytes': total})
        write(DEPLOY/'gpu_preflight.json', gpu_proof)
        replicas = [{'id': f'qwen25-{i}', 'gpu': ','.join(visible[2*i:2*i+2]), 'port': 19271+i,
                     'model_key': 'qwen25', 'replica_index': i, 'alias': MODEL_ALIAS,
                     'base_url': f'http://127.0.0.1:{19271+i}/v1', 'status': 'planned'} for i in range(REPLICA_COUNT)]
        state['replicas'] = replicas
        # One shared checkpoint is verified once; stagger pairs to bound shared-storage pressure.
        for offset in range(0, REPLICA_COUNT, 2):
            batch = replicas[offset:offset+2]
            for replica in batch:
                if STOP:
                    raise InterruptedError('Deployment stopped')
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', replica['port']))
                cmd = command(replica)
                write(run/(replica['id']+'_command.json'), {'argv': cmd, 'gpu': replica['gpu']})
                with (run/(replica['id']+'.log')).open('ab', buffering=0) as log:
                    proc = subprocess.Popen(cmd, cwd=ROOT, env=environment(run, replica),
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        start_new_session=True, close_fds=True)
                children[replica['id']] = proc
                replica.update(pid=proc.pid, status='starting')
                status(status='starting_services')
            deadline = time.monotonic()+2400
            while not all(replica['status'] == 'healthy' for replica in batch):
                if STOP:
                    raise InterruptedError('Deployment stopped during startup')
                for replica in batch:
                    if children[replica['id']].poll() is not None:
                        raise RuntimeError(replica['id']+': server exited during startup')
                    if replica['status'] != 'healthy' and healthy(replica):
                        state['synthetic_smoke_calls'] += 1
                        write(run/(replica['id']+'_smoke.json'), smoke(replica, tokenizer))
                        replica.update(status='healthy', healthy_at=now())
                        status(status='starting_services')
                if time.monotonic() > deadline:
                    raise TimeoutError('Service startup exceeded forty minutes')
                time.sleep(3)
        model_cfg = {'alias': MODEL_ALIAS, 'checkpoint': MODEL_REPO, 'model_revision': MODEL_REVISION,
                     'base_urls': [r['base_url'] for r in replicas], 'tokenizer_path': str(MODEL_PATH),
                     'chat_template_kwargs': {}, 'trust_remote_code': False, 'max_model_len': MAX_MODEL_LEN,
                     'dtype': 'float16', 'quantization': 'awq', 'tensor_parallel_size': TP_SIZE,
                     'kv_cache_dtype': 'auto_model_float16', 'hf_overrides': HF_OVERRIDES}
        write(ROOT/'endpoints.json', {'job_id': JOB, 'hostname': socket.gethostname(),
            'models': {'qwen25': model_cfg}, 'replicas': replicas, 'ready_at': now(),
            'service_supervisor_pid': os.getpid(), 'service_step_id': os.environ.get('SLURM_STEP_ID')})
        endpoint_published = True
        status(status='ready')
        failures = {replica['id']: 0 for replica in replicas}
        while not STOP:
            for replica in replicas:
                if children[replica['id']].poll() is not None:
                    raise RuntimeError(replica['id']+': server exited')
                failures[replica['id']] = 0 if healthy(replica) else failures[replica['id']]+1
                if failures[replica['id']] >= 3:
                    raise RuntimeError(replica['id']+': three failed health checks')
            status(status='ready', health_failures=failures)
            for _ in range(30):
                if STOP:
                    break
                time.sleep(1)
        status(status='stopping', reason='Supervisor received termination signal')
        return 0
    except BaseException as exc:
        status(status='failed', error_type=type(exc).__name__, reason=str(exc))
        return 1
    finally:
        if endpoint_published and (ROOT/'endpoints.json').exists():
            (ROOT/'endpoints.json').replace(DEPLOY/'endpoints_retired.json')
        cleanup(children)
        if state['status'] == 'stopping':
            status(status='stopped', stopped_at=now())
        lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
