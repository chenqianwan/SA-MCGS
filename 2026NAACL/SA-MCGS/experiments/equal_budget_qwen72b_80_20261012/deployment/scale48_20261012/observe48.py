#!/usr/bin/env python3
"""Read-only five-minute observation of the explicitly requested 48-worker run."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen
import json
import re
import statistics
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
KEYS = ('num_requests_running', 'num_requests_waiting', 'kv_cache_usage_perc',
        'num_preemptions_total', 'generation_tokens_total', 'prompt_tokens_total',
        'request_success_total')


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def service_metrics(port):
    with urlopen('http://127.0.0.1:' + str(port) + '/metrics', timeout=10) as response:
        raw = response.read().decode()
    result = {'port': port, 'server_error_or_abort': 0.0}
    for line in raw.splitlines():
        if line.startswith('#'):
            continue
        for key in KEYS:
            if line.startswith('vllm:' + key + '{') or line.startswith('vllm:' + key + ' '):
                value = float(line.rsplit(' ', 1)[1])
                if key == 'request_success_total':
                    if 'finished_reason="error"' in line or 'finished_reason="abort"' in line:
                        result['server_error_or_abort'] += value
                else:
                    result[key] = result.get(key, 0.0) + value
    if not all(key in result for key in KEYS[:-1]):
        raise RuntimeError('Expected vLLM counters are unavailable')
    return result


def main():
    output = HERE / 'performance_48.json'
    state = {'status': 'waiting_for_48', 'started_unix': time.time(),
             'scientific_model_calls': 0, 'samples': [],
             'comparison_caveat': 'A short observation of continuing scientific work; case mix and prefix cache vary.'}
    save(output, state)
    deadline = time.monotonic() + 2400
    try:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('48-worker startup was not verified within forty minutes')
            try:
                workers = read(ROOT / 'execution/status.json')
                service = read(ROOT / 'deployment/service_state.json')
                configured = read(ROOT / 'execution_config.json')
                if (workers['status'] == 'running' and workers['running_workers'] == 48
                        and configured == {'workers_per_replica': {'qwen25': 12}}
                        and service['status'] == 'ready'):
                    proofs = {}
                    for index in range(4):
                        path = ROOT / 'deployment/runtime/415747' / ('qwen25-' + str(index) + '_command.json')
                        argv = read(path)['argv']
                        if argv[argv.index('--max-num-seqs') + 1] != '12':
                            raise RuntimeError('Server execution limit does not equal twelve')
                        proofs[str(index)] = argv
                    state.update(status='observing', verified_workers=48,
                                 service_max_num_seqs=12, service_pid=service['pid'],
                                 server_commands=proofs, observation_started_unix=time.time())
                    break
            except FileNotFoundError:
                pass
            time.sleep(5)
        for sample_index in range(31):
            with ThreadPoolExecutor(max_workers=4) as pool:
                rows = list(pool.map(service_metrics, range(19271, 19275)))
            workers = read(ROOT / 'execution/status.json')
            sample = {'observed_unix': time.time(), 'services': rows,
                      'running_workers': workers['running_workers'],
                      'worker_status': workers['status'], 'final_arms': workers['final_results']}
            if state['samples']:
                previous = state['samples'][-1]
                elapsed = sample['observed_unix'] - previous['observed_unix']
                sample['generation_tokens_per_second'] = sum(
                    now['generation_tokens_total'] - before['generation_tokens_total']
                    for now, before in zip(rows, previous['services'])) / elapsed
            state['samples'].append(sample)
            state.update(updated_unix=time.time(), latest=sample)
            if any(row['server_error_or_abort'] for row in rows) or workers['status'] != 'running':
                state['attention_reason'] = 'Observed a server abort/error or a worker state requiring inspection'
            save(output, state)
            if sample_index < 30:
                time.sleep(10)
        # Exclude the first minute of this observation to reduce initial prefill effects.
        retained = state['samples'][6:]
        first, last = retained[0], retained[-1]
        seconds = last['observed_unix'] - first['observed_unix']
        speed = sum(after['generation_tokens_total'] - before['generation_tokens_total']
                    for after, before in zip(last['services'], first['services'])) / seconds
        baseline_path = ROOT / 'deployment/concurrency_20261012/verification_stable.json'
        baseline = read(baseline_path)['generation_tokens_per_second'] if baseline_path.exists() else None
        state.update(status='observed_needs_review' if state.get('attention_reason') else 'observation_complete',
                     ended_unix=time.time(), measured_generation_tokens_per_second=speed,
                     baseline_32_generation_tokens_per_second=baseline,
                     observed_gain_percent=(speed / baseline - 1) * 100 if baseline else None,
                     max_active_requests=sum(max(sample['services'][i]['num_requests_running'] for sample in retained) for i in range(4)),
                     max_simultaneous_active_requests=max(sum(row['num_requests_running'] for row in sample['services']) for sample in retained),
                     peak_kv_cache_percent=max(row['kv_cache_usage_perc'] * 100 for sample in retained for row in sample['services']),
                     preemptions=sum(row['num_preemptions_total'] for row in last['services']),
                     max_waiting_requests=max(sum(row['num_requests_waiting'] for row in sample['services']) for sample in retained))
        save(output, state)
        print(json.dumps({k: v for k, v in state.items() if k not in ('samples', 'server_commands', 'latest')}), flush=True)
        return 0
    except BaseException as exc:
        state.update(status='observation_failed', error_type=type(exc).__name__, error=str(exc), ended_unix=time.time())
        save(output, state)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
