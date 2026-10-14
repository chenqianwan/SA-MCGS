#!/usr/bin/env python3
"""Versioned terminal-classification adapter around the unchanged Llama runner.

The original protocol remains the request/cache identity. Every new result also
binds this producer and the explicit amendment; no source hash is impersonated.
"""
from __future__ import annotations
import asyncio
import hashlib
import importlib.util
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / 'runner/llama_launcher.py'
spec = importlib.util.spec_from_file_location('frozen_llama_runner', ORIGINAL)
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)
ORIGINAL_VALIDATE = L.validate_result


def amendment():
    value = L.read(HERE / 'schema_amendment.json')
    if value['version'] != 1 or value['amendment_id'] != 'transposition_entry_validationerror_terminal_v1':
        raise L.IntegrityStop('Unknown terminal-classification amendment')
    if L.sha(ORIGINAL) != value['original_launcher_sha256']:
        raise L.IntegrityStop('Original scientific adapter changed')
    return value


def provenance(frozen):
    change = amendment()
    base = L.digest(frozen)
    if base != change['base_request_protocol_sha256']:
        raise L.IntegrityStop('Amendment does not cover this original protocol')
    fields = {'base_request_protocol_sha256': base,
              'schema_compat_adapter_sha256': L.sha(Path(__file__)),
              'schema_compat_amendment_sha256': L.sha(HERE / 'schema_amendment.json'),
              'schema_compat_amendment_id': change['amendment_id']}
    fields['terminalization_protocol_sha256'] = L.digest(fields)
    return fields


def is_model_validation_error(result):
    trace = str(result.get('traceback') or '')
    return (result.get('error_type') == 'ValidationError'
            and 'for TranspositionEntry' in str(result.get('cost_audit_error') or result.get('error') or '')
            and 'alphago_mcgs.py' in trace and 'TranspositionEntry(' in trace)


def classification(result):
    if not result.get('cost_audit_error'):
        return 'complete'
    if (result.get('error_type') in {'ValueError', 'TypeError', 'KeyError', 'AttributeError'}
            or is_model_validation_error(result)):
        return 'strict_experiment_failure'
    raise L.IntegrityStop(f'Unrecognized scientific implementation error: {result.get("error_type")}')


def validate_result(cost, args, case, method, graphs, frozen, result):
    ORIGINAL_VALIDATE(cost, args, case, method, graphs, frozen, result)
    marked = 'schema_compat_adapter_sha256' in result
    if marked:
        for key, expected in provenance(frozen).items():
            if result.get(key) != expected:
                raise L.IntegrityStop(f'Terminal-classification provenance mismatch: {key}')
    if result.get('error_type') == 'ValidationError':
        if (not marked or not is_model_validation_error(result)
                or result.get('completion_status') != 'strict_experiment_failure'):
            raise L.IntegrityStop('Unqualified ValidationError terminal result')


def replay_only_client_class(cost):
    """Use the original JSON parser and journal, but never send missing calls."""
    from src.llm.base import LLMResponse
    class ReplayOnly(L.make_client_class(cost)):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.pending = []
        async def call(self, prompt, *, temperature=0.0, max_tokens=4096,
                       system_prompt=None, response_format=None):
            request = L.request_payload(prompt, temperature, max_tokens, system_prompt, response_format)
            if L.token_count(self.tokenizer, request) + max_tokens > self.max_model_len:
                raise L.IntegrityStop('Cached request exceeds frozen context')
            if self.journal.next_index >= self.journal.original_start_count:
                raise L.IntegrityStop('Known failure replay attempted an unrecorded request')
            index, _ = self.journal.begin(request)
            saved = await self.journal.replay(index)
            if saved is None:
                self.pending.append(asyncio.current_task())
                await asyncio.Future()
                raise L.IntegrityStop('Uncached response must never be fabricated')
            if saved['returned_model'] != L.ALIAS:
                raise L.IntegrityStop('Cached model mismatch')
            self.call_records.append({**saved['record'], 'replayed_from_checkpoint': True,
                                      'schema_failure_recovery': True})
            self.last_usage = saved['usage']
            return LLMResponse(content=saved['content'], model=L.ALIAS,
                usage={k: int(saved['usage'].get(k, 0)) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')})
        async def close(self):
            for task in self.pending:
                if not task.done():
                    task.cancel()
            if self.pending:
                await asyncio.gather(*self.pending, return_exceptions=True)
            await super().close()
    return ReplayOnly


async def run_one(cost, args, case, method, graphs, frozen, tokenizer):
    binding = provenance(frozen)
    path = L.result_path(args, case, method)
    if path.exists():
        validate_result(cost, args, case, method, graphs, frozen, L.read(path))
        return
    known = amendment()['known_cached_failure']
    recover = case['case_id'] == known['case_id'] and method == known['method']
    cache = args.output_dir / 'call_cache' / case['case_id'] / method
    if recover:
        for name, expected in known['cache_files_sha256'].items():
            if L.sha(cache / name) != expected:
                raise L.IntegrityStop('Known-failure cache differs from audited evidence: ' + name)
    status_path = args.output_dir / 'case_status' / f"{case['case_id']}__{method}.json"
    L.write(status_path, {'case_id': case['case_id'], 'method': method, 'state': 'running',
                         'schema_compat_amendment_id': binding['schema_compat_amendment_id'], 'time': time.time()})
    graph, scc, root, metadata = cost.prepare_injected_case(case, graphs)
    cls = replay_only_client_class(cost) if recover else L.make_client_class(cost)
    client = cls(args, case, method, frozen, tokenizer)
    old = cost.make_llm
    cost.make_llm = lambda *_a, **_k: client
    random.seed(42)
    try:
        result = await cost.run_method(L.scientific_args(args), args.output_dir, case, method,
                                      graph, scc, root, metadata)
        client.journal.assert_consumed()
        if recover:
            if not is_model_validation_error(result):
                raise L.IntegrityStop('Audited cached schema failure did not reproduce')
            for name, expected in known['cache_files_sha256'].items():
                if L.sha(cache / name) != expected:
                    raise L.IntegrityStop('Known-failure replay changed cached evidence')
        state = classification(result)
        if method == 'lea' and state == 'complete':
            ranking = result.get('ranking') or []
            result['top1_hit'] = bool(ranking and ranking[0][0] == root)
            result['top3_hit'] = root in [row[0] for row in ranking[:3]]
        result.update({'completion_status': state, 'protocol_sha256': L.digest(frozen),
            'checkpoint_repository': L.CHECKPOINT, 'checkpoint_revision': args.checkpoint_revision,
            'base_url': args.base_url, 'requested_model_id': L.ALIAS,
            'case_concurrency': args.case_concurrency, 'internal_concurrency': 8 if method == 'sa-mcgs' else 1,
            'python_rng_seed': 42, 'json_parse_exhausted_windows': client.parse_exhausted_windows,
            'external_api_cost_usd': 0.0, 'main_case_order': case['main_case_order'],
            'main_case_id': case['main_case_id'], **binding,
            'terminalization_policy_note': 'Original request/scientific protocol is retained; actual result producer and amended schema-failure classification are separately bound above.',
            'cached_only_schema_recovery': recover})
        if recover:
            result['schema_recovery_audit'] = {'source_job_id': known['source_job_id'],
                'new_api_calls': 0, 'cached_completion_order': client.journal.order,
                'original_request_starts': client.journal.original_start_count,
                'consumed_request_starts': client.journal.next_index,
                'consumed_cached_responses': client.journal.cursor,
                'uncached_requests_held_without_network': len(client.pending),
                'cache_files_sha256': known['cache_files_sha256']}
        validate_result(cost, args, case, method, graphs, frozen, result)
        L.write(path, result)
        L.write(status_path, {'case_id': case['case_id'], 'method': method, 'state': state,
            'result_sha256': L.sha(path), **binding, 'time': time.time()})
        print(L.json.dumps({'case': case['main_case_order'], 'method': method, 'state': state,
              'cached_only_schema_recovery': recover, 'amendment': binding['schema_compat_amendment_id']}), flush=True)
    except BaseException as exc:
        L.write(status_path, {'case_id': case['case_id'], 'method': method,
            'state': 'provider_failure' if isinstance(exc, L.ProviderFailure) else 'interrupted_or_integrity_stop',
            'error_type': type(exc).__name__, 'message': str(exc)[:1000], 'time': time.time()})
        raise
    finally:
        cost.make_llm = old


L.run_one = run_one
L.validate_result = validate_result

if __name__ == '__main__':
    try:
        amendment()
        raise SystemExit(asyncio.run(L.main(L.parse_args())))
    except L.RunStop as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(3)
