"""Read-only compact status; pipe this script to the existing SSH login host."""
from pathlib import Path
import json
import time

ROOT = Path('/aifs4su/hansirui_3rd/chenlong/mcgs_law/equal_budget_qwen72b_80_20261012')
HERE = ROOT / 'deployment/scale48_20261012'
print('OBSERVED', time.strftime('%Y-%m-%d %H:%M:%S %Z'))
files = {
    'controller_status.json': ['status', 'pid', 'step_id', 'updated_unix', 'error'],
    'checkpoint_status.json': ['status', 'paused_worker_count', 'accounted_worker_count',
                               'naturally_exited_worker_count', 'updated_at', 'error', 'partial_termination'],
    'replay_preflight_frozen.json': ['status', 'arm_count', 'all_active_arms_verified', 'provider_calls', 'errors'],
    'drained_receipt.json': ['status', 'completed_at', 'claim_locks_release'],
    'restart_receipt.json': ['status', 'new_workers_per_replica', 'new_service_max_num_seqs', 'pipeline_exit_code'],
    'performance_48.json': ['status', 'verified_workers', 'service_max_num_seqs',
                           'measured_generation_tokens_per_second', 'observed_gain_percent',
                           'max_simultaneous_active_requests', 'peak_kv_cache_percent', 'preemptions',
                           'max_waiting_requests', 'attention_reason', 'error'],
}
for name, keys in files.items():
    path = HERE / name
    if path.exists():
        value = json.loads(path.read_text())
        result = {k: value[k] for k in keys if k in value}
        if name == 'checkpoint_status.json':
            all_names = {f'qwen25-{r}_worker{i}' for r in range(4) for i in range(8)}
            result['unpaused_workers'] = sorted(all_names - set(value.get('frozen_workers', {})))
        if name == 'performance_48.json':
            result['sample_count'] = len(value.get('samples', []))
            result['latest'] = value.get('latest')
        print(name, json.dumps(result))
for name, keys in {
    'execution/status.json': ['status', 'pid', 'step_id', 'running_workers', 'final_results', 'error'],
    'deployment/pipeline_status.json': ['status', 'pid', 'step_id', 'updated_at', 'error'],
    'deployment/service_state.json': ['status', 'pid', 'step_id', 'updated_at', 'health_failures', 'reason'],
}.items():
    path = ROOT / name
    if path.exists():
        value = json.loads(path.read_text())
        print(name, json.dumps({k: value[k] for k in keys if k in value}))
for name in ('checkpoint_step.log', 'replay_preflight_frozen.log', 'restart_step.log'):
    path = HERE / name
    if path.exists():
        print(name, '\n'.join(path.read_text(errors='replace').splitlines()[-2:]))

print("UNPAUSED_REQUESTS")
cs=json.loads((ROOT/'deployment/scale48_20261012/checkpoint_status.json').read_text())
for name in cs.get('watched_processes', {}):
    if not name.startswith('qwen25-') or name in cs.get('frozen_workers', {}): continue
    row=json.loads((ROOT/'execution'/(name+'_status.json')).read_text())
    uid,method=row.get('current_case_uid'),row.get('current_method')
    ledger=ROOT/'results/qwen25'/str(uid)/str(method)/'ledger.jsonl'
    if ledger.exists():
        events=[json.loads(x) for x in ledger.read_bytes().splitlines()]
        reserve=[r for r in events if r.get('event')=='reserve']
        last=events[-1]
        print(json.dumps({'worker':name,'method':method,'last_reserve':reserve[-1] if reserve else None,'last_event':last},ensure_ascii=False))
