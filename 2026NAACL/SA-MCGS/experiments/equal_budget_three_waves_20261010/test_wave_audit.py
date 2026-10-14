"""Synthetic offline fixtures only: no inference clients, downloads or network."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from wave_audit import HEADER, audit_model, digest, sha


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False)+'\n')


def write_ledger(path, events):
    path.write_text(''.join(json.dumps(e)+'\n' for e in events))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.uids = [f'case-{i:03d}' for i in range(80)]
        scope = {'cases_per_model': 80, 'expected_results': 480,
                 'execution_methods': ['lea', 'full-scc'], 'case_uids': self.uids}
        write(self.root/'run_scope.json', scope)
        refs = []
        for model in ('llama', 'kimi', 'qwen35'):
            for i, uid in enumerate(self.uids):
                refs.append({'model_key': model, 'case_uid': uid, 'case_id': f'id-{i}',
                             'main_case_order': i+1, 'domain': '测试', 'source_n': 2,
                             'method': 'sa-mcgs', 'completion_status': 'complete',
                             'usage': {'total_tokens': 100}, 'source_sha256': digest([model, uid])})
        write(self.root/'historical_sa_reference.json', {'rows': refs})
        planpath = self.root/'science/repo/portable_data/qwen80_case_plan.json'
        write(planpath, [{'case_uid': uid, 'case_id': f'current-id-{i}'} for i, uid in enumerate(self.uids)])
        protocol = {'run_scope': scope, 'run_scope_sha256': sha(self.root/'run_scope.json'),
                    'case_plan_sha256': sha(planpath),
                    'historical_sa_reference_sha256': sha(self.root/'historical_sa_reference.json'),
                    'models_configuration': {'llama': {'alias': 'served-llama'}}, 'seed': 42}
        write(self.root/'protocol.json', protocol)
        self.phash = digest(protocol)
        for ref in refs[:80]:
            for method in ('lea', 'full-scc'):
                self.arm(ref, method)
        self.folder = self.root/'results/llama'/self.uids[0]/'lea'

    def tearDown(self):
        self.temp.cleanup()

    def arm(self, ref, method):
        uid = ref['case_uid']
        folder = self.root/'results/llama'/uid/method
        folder.mkdir(parents=True)
        owner = [uid, 'served-llama', method]
        events = [HEADER,
            {'event': 'owner', 'owner': owner, 'token_cap': 100, 'fingerprint': 'a'*64},
            {'event': 'reserve', 'owner': owner, 'call_id': 'sample', 'request_key': 'call-00000000:attempt-0',
             'request_hash': 'b'*64, 'phase': 'candidate', 'input_tokens': 10,
             'max_output_tokens': 20, 'requested_max_output_tokens': 20, 'reserved_tokens': 30,
             'selector_reserve': 0, 'retry_index': 0, 'cache_file': 'calls/request.json'},
            {'event': 'finish', 'call_id': 'sample', 'status': 'completed_with_usage',
             'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
             'prompt_tokens': 10, 'completion_tokens': 5, 'actual_total_tokens': 15,
             'usage_issues': [], 'elapsed_seconds': .25, 'response_sha256': 'c'*64},
            {'event': 'parse', 'call_id': 'sample', 'outcome': 'dict'}]
        write_ledger(folder/'ledger.jsonl', events)
        usage = {'calls': 1, 'completed_with_usage': 1, 'held_calls': 0, 'pending_calls': 0,
                 'unknown_failure_calls': 0, 'missing_usage_calls': 0, 'recovered_unresolved_calls': 0,
                 'retry_calls': 0, 'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15,
                 'held_tokens': 0, 'accounted_tokens': 15, 'provider_seconds': .25,
                 'usage_mismatch_calls': 0, 'parse_failure_calls': 0, 'external_api_calls': 0}
        row = {'model_key': 'llama', 'model': 'served-llama', 'case_uid': uid, 'method': method,
               'case_id': f"current-id-{ref['main_case_order']-1}", 'domain': ref['domain'], 'source_n': ref['source_n'],
               'main_case_order': ref['main_case_order'], 'protocol_sha256': self.phash,
               'historical_sa_source_sha256': ref['source_sha256'],
               'historical_sa_completion_status': ref['completion_status'], 'token_budget': 100,
               'visible_input_sha256': 'd'*64, 'completion_status': 'complete', 'usage': usage}
        write(folder/'final.json', row)
        write(folder/'input_identity.json', {k: row[k] for k in ('case_uid', 'method', 'protocol_sha256',
            'token_budget', 'historical_sa_source_sha256', 'visible_input_sha256')})

    def mutate_final(self, fn):
        path = self.folder/'final.json'
        row = json.loads(path.read_text())
        fn(row)
        write(path, row)

    def mutate_ledger(self, fn):
        path = self.folder/'ledger.jsonl'
        events = [json.loads(line) for line in path.read_text().splitlines()]
        fn(events)
        write_ledger(path, events)

    def assert_error(self, reason):
        result = audit_model(self.root, 'llama')
        self.assertFalse(result['complete'])
        self.assertTrue(any(reason in r['reason'] for r in result['errors']), result)
        return result

    def test_complete_canonical_unicode_digest_and_read_only(self):
        self.mutate_final(lambda r: r.update(completion_status='strict_experiment_failure'))
        before = {str(p): (p.stat().st_mtime_ns, sha(p)) for p in self.root.rglob('*') if p.is_file()}
        result = audit_model(self.root, 'llama')
        self.assertTrue(result['complete'], result)
        self.assertEqual((result['terminal_count'], result['verified_count'], result['strict_failures']), (160, 160, 1))
        self.assertEqual(result['actual_tokens'], 2400)
        after = {str(p): (p.stat().st_mtime_ns, sha(p)) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_final_is_pending_not_error(self):
        (self.folder/'final.json').unlink()
        result = audit_model(self.root, 'llama')
        self.assertFalse(result['complete'])
        self.assertEqual(result['terminal_count'], 159)
        self.assertEqual(result['missing'], [{'case_uid': self.uids[0], 'method': 'lea'}])
        self.assertEqual(result['errors'], [])
        for p in (self.root/'results').rglob('final.json'):
            p.unlink()
        (self.root/'protocol.json').unlink()
        result = audit_model(self.root, 'llama')
        self.assertEqual(len(result['missing']), 160)
        self.assertEqual(result['errors'], [])

    def test_historical_display_id_can_differ_from_execution_plan(self):
        historical = json.loads((self.root/'historical_sa_reference.json').read_text())['rows'][0]
        final = json.loads((self.folder/'final.json').read_text())
        self.assertNotEqual(final['case_id'], historical['case_id'])
        self.assertEqual(final['case_uid'], historical['case_uid'])
        self.assertTrue(audit_model(self.root, 'llama')['complete'])
        self.mutate_final(lambda r: r.update(case_id=historical['case_id']))
        self.assert_error('final_identity_or_protocol_mismatch:case_id')

    def test_cross_wave_protocol_and_path_pollution_rejected(self):
        self.mutate_final(lambda r: r.update(protocol_sha256='f'*64))
        self.assert_error('final_identity_or_protocol_mismatch')
        self.mutate_final(lambda r: r.update(protocol_sha256=self.phash, method='full-scc'))
        self.assert_error('final_identity_or_protocol_mismatch')
        extra = self.root/'results/llama/foreign-case/lea/final.json'
        write(extra, {})
        self.assert_error('extra_or_duplicate_arm')

    def test_historical_budget_and_final_counter_mismatch(self):
        self.mutate_final(lambda r: r.update(token_budget=101))
        self.assert_error('final_historical_budget_mismatch')
        self.mutate_final(lambda r: r.update(token_budget=100))
        self.mutate_final(lambda r: r['usage'].update(calls=2))
        self.assert_error('final_ledger_counter_mismatch:calls')

    def test_unknown_usage_duplicate_settlement_and_budget_overrun(self):
        original = (self.folder/'ledger.jsonl').read_text()
        self.mutate_ledger(lambda rows: rows[3].update(status='unknown_failure', error_type='TimeoutError'))
        self.assert_error('unknown_or_held_provider_usage')
        (self.folder/'ledger.jsonl').write_text(original)
        self.mutate_ledger(lambda rows: rows.append(rows[3]))
        self.assert_error('unknown_or_duplicate_settlement')
        (self.folder/'ledger.jsonl').write_text(original)
        self.mutate_ledger(lambda rows: rows[2].update(max_output_tokens=100, requested_max_output_tokens=100, reserved_tokens=110))
        self.assert_error('reservation_exceeds_budget')

    def test_shared_ledger_and_outside_arm_cache_rejected(self):
        other = self.folder.parent/'full-scc/ledger.jsonl'
        other.unlink()
        os.link(self.folder/'ledger.jsonl', other)
        self.assert_error('shared_or_hardlinked_ledger')
        other.unlink()
        self.mutate_ledger(lambda rows: rows[2].update(cache_file='../full-scc/calls/request.json'))
        self.assert_error('shared_or_outside_arm_cache')

    def test_recovered_cache_diagnostic_is_not_unknown_usage(self):
        self.mutate_final(lambda r: r['usage'].update(recovered_unresolved_calls=1))
        self.assertTrue(audit_model(self.root, 'llama')['complete'])


if __name__ == '__main__':
    unittest.main()
