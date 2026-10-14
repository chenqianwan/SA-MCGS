#!/usr/bin/env python3
"""Targeted offline verification using the actual failed cached responses."""
from __future__ import annotations
import argparse
import asyncio
import copy
import os
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch
import schema_compat_launcher as A

L = A.L
HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'diagnostics/case15_sa_validationerror_20260924/remote/results/llama80_three_methods'

class Tokenizer:
    def apply_chat_template(self, *_args, **_kwargs):
        return [1]

async def main():
    if os.environ.get('PYTHONHASHSEED') != '42':
        raise RuntimeError('PYTHONHASHSEED=42 required')
    os.environ['LOCAL_VLLM_API_KEY'] = 'offline-verification-only'
    cost = L.import_science()
    graphs = L.restore_graphs(cost, L.verify_bundle())
    plan = L.read(L.ROOT / 'portable_data/llama80_case_plan.json')
    for case in plan:
        case['source_result_file'] = str(L.ROOT / case['source_result_repo_relpath'])
    cost.validate_case_plan(plan, graphs)
    case = next(c for c in plan if c['main_case_order'] == 15)
    frozen = L.read(SOURCE / 'frozen_protocol.json')
    before_source = {n: L.sha(SOURCE / 'call_cache' / case['case_id'] / 'sa-mcgs' / n)
                     for n in ('requests.jsonl', 'responses.jsonl')}
    calls = []
    async def forbid_network(*args, **kwargs):
        calls.append(True)
        raise AssertionError('No network request is allowed during this verification')
    with tempfile.TemporaryDirectory(prefix='schema-compat-verification-') as temporary:
        output = Path(temporary)
        cache = output / 'call_cache' / case['case_id'] / 'sa-mcgs'
        shutil.copytree(SOURCE / 'call_cache' / case['case_id'] / 'sa-mcgs', cache)
        args = argparse.Namespace(output_dir=output, base_url='http://127.0.0.1:18081/v1',
            llm_timeout=600, case_concurrency=8, shard_count=8, shard_index=6,
            mode='run', max_model_len=131072, checkpoint_revision=frozen['checkpoint_revision'])
        assert L.protocol(args, cost, L.verify_bundle()) == frozen
        with patch('openai.resources.chat.completions.AsyncCompletions.create', forbid_network):
            await asyncio.wait_for(A.run_one(cost, args, case, 'sa-mcgs', graphs, frozen, Tokenizer()), 20)
        result_path = L.result_path(args, case, 'sa-mcgs')
        result = L.read(result_path)
        assert result['completion_status'] == 'strict_experiment_failure'
        assert result['error_type'] == 'ValidationError'
        assert 'conflicts.2' in result['error'] and 'critical_pairs' in result['error']
        assert 'TranspositionEntry(' in result['traceback']
        assert result['llm_usage_summary']['successful_api_calls'] == 2
        assert result['llm_usage_summary']['failed_api_calls'] == 0
        assert result['schema_recovery_audit']['new_api_calls'] == 0
        assert result['schema_recovery_audit']['uncached_requests_held_without_network'] == 6
        assert result['schema_recovery_audit']['cached_completion_order'] == [7, 6]
        assert result['schema_recovery_audit']['consumed_request_starts'] == 8
        assert not (output / 'call_logs').exists()
        for key, value in A.provenance(frozen).items():
            assert result[key] == value
        assert before_source == {n: L.sha(cache / n) for n in before_source}
        assert before_source == {n: L.sha(SOURCE / 'call_cache' / case['case_id'] / 'sa-mcgs' / n) for n in before_source}
        before_result = L.sha(result_path)
        await A.run_one(cost, args, case, 'sa-mcgs', graphs, frozen, Tokenizer())
        assert L.sha(result_path) == before_result
        summary = L.summarize(args, plan, cost, graphs, frozen)
        assert summary['methods']['sa-mcgs']['risk_all'] == 0.0
        assert summary['methods']['sa-mcgs']['root_at3'] == 0.0
        assert summary['methods']['sa-mcgs']['compression_valid_only'] is None

        # Existing legacy terminal observations retain their original bytes.
        legacy_case = next(c for c in plan if c['main_case_order'] == 20)
        _, scc, _, metadata = cost.prepare_injected_case(copy.deepcopy(legacy_case), graphs)
        legacy = {**metadata, 'model': L.MODEL, 'case_id': legacy_case['case_id'],
            'cost_audit_method': 'lea', 'protocol_sha256': L.digest(frozen),
            'completion_status': 'complete', 'case_concurrency': 2,
            'scc_clause_ids': list(scc.clause_ids), 'scc_size': scc.size,
            'ranking': [[scc.clause_ids[0], 0.5]], 'lea_risk_subgraph_nodes': list(scc.clause_ids[:4])}
        legacy_path = L.result_path(args, legacy_case, 'lea')
        L.write(legacy_path, legacy)
        legacy_sha = L.sha(legacy_path)
        await A.run_one(cost, args, legacy_case, 'lea', graphs, frozen, Tokenizer())
        assert L.sha(legacy_path) == legacy_sha
        assert 'schema_compat_adapter_sha256' not in L.read(legacy_path)

        # Neither infrastructure failures nor unrelated Pydantic failures qualify.
        for subtype in ('RuntimeError', 'ProviderFailure', 'ValidationError'):
            try:
                A.classification({'error_type': subtype, 'cost_audit_error': 'unrelated implementation/configuration failure', 'traceback': 'configuration.py'})
            except L.IntegrityStop:
                pass
            else:
                raise AssertionError('Unrelated failure was accepted as model schema failure')
        assert A.classification({'error_type': 'ValueError', 'cost_audit_error': 'old-format-error'}) == 'strict_experiment_failure'
        forged = copy.deepcopy(result)
        forged['schema_compat_adapter_sha256'] = '0' * 64
        try:
            A.validate_result(cost, args, case, 'sa-mcgs', graphs, frozen, forged)
        except L.IntegrityStop:
            pass
        else:
            raise AssertionError('Forged producer hash was accepted')
        assert not calls
        report = {'passed': True, 'api_calls': 0, 'actual_bad_cache_replayed': True,
            'original_request_starts_consumed': 8, 'cached_completion_order': [7, 6],
            'uncached_requests_held_without_network': 6, 'source_and_replayed_cache_bytes_unchanged': True,
            'raw_error_subtype_message_traceback_preserved': True,
            'terminal_result_reuse_unchanged': True, 'legacy_terminal_bytes_unchanged': True,
            'schema_failure_detection_scores_zero': True, 'invalid_compression_is_null': True,
            'unknown_implementation_and_configuration_errors_rejected': True,
            'forged_adapter_provenance_rejected': True,
            'old_launcher_sha256': L.sha(A.ORIGINAL), **A.provenance(frozen),
            'error': result['error'], 'error_type': result['error_type']}
        L.write(HERE / 'schema_compat_verification.json', report)
        L.write(HERE / 'verification.json', report)
        print(L.json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
