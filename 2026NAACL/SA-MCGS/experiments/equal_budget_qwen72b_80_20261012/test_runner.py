"""Offline scope, provenance, resume and no-SA safety checks (no inference)."""
import asyncio
import concurrent.futures
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner


def fixture():
    plan = [{'case_uid': f'case-{i:02d}', 'main_case_order': i + 1,
             'domain': 'cuad', 'planned_scc_clause_ids': ['a', 'b']}
            for i in range(80)]
    scope = {'scope_schema': 'historical_sa_baselines_v1', 'models': ['qwen25'],
             'cases_per_model': 80, 'expected_results': 160, 'comparison_expected_results': 240,
             'execution_methods': ['lea', 'full-scc'], 'sa_execution_enabled': False,
             'stop_after_scope': True, 'case_uids': [c['case_uid'] for c in plan]}
    reference = {'budget_provenance': {'kind': 'calibrated', 'description': 'Explicit offline test values'},
                 'rows': [{'model_key': 'qwen25', 'model': runner.MODEL_ALIAS,
                           'method': 'sa-mcgs', 'case_uid': c['case_uid'], 'domain': c['domain'],
                           'source_n': 2, 'source_sha256': 'a' * 64,
                           'completion_status': 'complete', 'usage': {'total_tokens': (i + 1) * 100}}
                          for i, c in enumerate(plan)]}
    return plan, scope, reference


def final_row(case, method, ref):
    return {'model_key': 'qwen25', 'model': runner.MODEL_ALIAS, 'case_uid': case['case_uid'],
            'method': method, 'protocol_sha256': 'f' * 64, 'completion_status': 'complete',
            'token_budget': ref['usage']['total_tokens'], 'historical_sa_source_sha256': ref['source_sha256'],
            'usage': {'total_tokens': 10, 'accounted_tokens': 10, 'held_calls': 0, 'usage_mismatch_calls': 0}}


class ScopeQueueTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.patch = patch.object(runner, 'ROOT', self.root)
        self.patch.start()
        self.plan, self.scope, self.reference = fixture()
        runner.save(self.root/'run_scope.json', self.scope)
        runner.save(self.root/'historical_sa_reference.json', self.reference)

    def tearDown(self):
        self.patch.stop()
        self.directory.cleanup()

    def test_80_independent_case_identities_produce_exactly_160_baseline_arms(self):
        scope = runner.load_scope(self.plan)
        refs = runner.historical_reference(self.plan)
        tasks = runner.ordered_tasks(self.plan, refs, 'qwen25')
        self.assertEqual(len({c['case_uid'] for c, _ in tasks}), 80)
        self.assertEqual(len({(c['case_uid'], m) for c, m in tasks}), 160)
        self.assertEqual({m for _, m in tasks}, {'lea', 'full-scc'})
        caps = [refs[('qwen25', c['case_uid'])]['usage']['total_tokens'] for c, _ in tasks]
        self.assertEqual(caps, sorted(caps, reverse=True))
        self.assertFalse(scope['sa_execution_enabled'])

    def test_scope_rejects_extra_case_duplicate_model_sa_and_wrong_counts(self):
        changes = [{'models': ['qwen35']}, {'execution_methods': ['lea', 'full-scc', 'sa-mcgs']},
                   {'expected_results': 161}, {'sa_execution_enabled': True},
                   {'case_uids': self.scope['case_uids'] + ['extra']},
                   {'case_uids': [self.scope['case_uids'][0]] * 80}]
        for change in changes:
            with self.subTest(change=change):
                runner.save(self.root/'run_scope.json', {**self.scope, **change})
                with self.assertRaises(runner.WorkerStop):
                    runner.load_scope(self.plan)

    def test_reference_rejects_wrong_model_method_case_source_and_implicit_provenance(self):
        changes = [{'model_key': 'qwen35'}, {'model': 'llama-3'}, {'method': 'lea'},
                   {'case_uid': 'unknown'}, {'source_n': 3}, {'usage': {'total_tokens': True}},
                   {'source_sha256': 'z' * 64}, {'budget_provenance': {'kind': 'unknown'}}]
        for change in changes:
            with self.subTest(change=change):
                document = copy.deepcopy(self.reference)
                document['rows'][0].update(change)
                runner.save(self.root/'historical_sa_reference.json', document)
                with self.assertRaises(runner.WorkerStop):
                    runner.historical_reference(self.plan)
        document = copy.deepcopy(self.reference)
        document.pop('budget_provenance')
        runner.save(self.root/'historical_sa_reference.json', document)
        with self.assertRaises(runner.WorkerStop):
            runner.historical_reference(self.plan)

    def test_actual_and_calibrated_are_both_explicitly_accepted(self):
        for kind in ('actual', 'calibrated'):
            self.reference['budget_provenance']['kind'] = kind
            runner.save(self.root/'historical_sa_reference.json', self.reference)
            self.assertEqual(len(runner.historical_reference(self.plan)), 80)

    def test_two_workers_claim_separate_arms_and_resume_skips_completed(self):
        case = self.plan[0]
        tasks = [(case, 'lea'), (case, 'full-scc')]
        refs = runner.historical_reference(self.plan)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: runner.claim_next(tasks, 'qwen25', refs), range(2)))
        self.assertEqual({claimed[1] for claimed in claims}, {'lea', 'full-scc'})
        self.assertIsNone(runner.claim_next(tasks, 'qwen25', refs))
        for case, method, lock in claims:
            path = self.root/'results/qwen25'/case['case_uid']/method/'final.json'
            runner.save(path, final_row(case, method, refs[('qwen25', case['case_uid'])]))
            lock.close()
        self.assertIsNone(runner.claim_next(tasks, 'qwen25', refs))
        self.assertEqual(len(runner.validate_existing_results(self.scope, refs)), 2)

    def test_corrupt_or_failed_final_is_not_silently_skipped(self):
        case = self.plan[0]
        refs = runner.historical_reference(self.plan)
        row = final_row(case, 'lea', refs[('qwen25', case['case_uid'])])
        path = self.root/'results/qwen25'/case['case_uid']/'lea/final.json'
        for changes in ({'model_key': 'qwen35'}, {'completion_status': 'infrastructure_failure'},
                        {'token_budget': 1}, {'protocol_sha256': 'changed'}):
            with self.subTest(changes=changes):
                runner.save(path, {**row, **changes})
                with self.assertRaises(runner.WorkerStop):
                    runner.claim_next([(case, 'lea')], 'qwen25', refs, 'f' * 64)

    def test_no_sa_or_other_model_can_be_claimed_or_executed(self):
        for model, method in [('qwen25', 'sa-mcgs'), ('qwen35', 'lea')]:
            with self.assertRaises(runner.WorkerStop):
                runner.claim_next([(self.plan[0], method)], model)
            with self.assertRaises(runner.WorkerStop):
                asyncio.run(runner.run_arm(self.plan[0], method, {'model_key': model},
                                          None, None, None, None, None, None, None))

    def test_out_of_scope_existing_result_rejected(self):
        case = self.plan[0]
        refs = runner.historical_reference(self.plan)
        for model, uid, method in [('qwen35', case['case_uid'], 'lea'),
                                   ('qwen25', 'extra', 'lea'),
                                   ('qwen25', case['case_uid'], 'sa-mcgs')]:
            path = self.root/'results'/model/uid/method/'final.json'
            runner.save(path, {})
            with self.assertRaises(runner.WorkerStop):
                runner.validate_existing_results(self.scope, refs)
            path.unlink()

    def test_endpoint_identity_and_context_guard(self):
        valid = {'models': {'qwen25': {'alias': runner.MODEL_ALIAS,
                    'checkpoint': runner.MODEL_CHECKPOINT, 'max_model_len': 32768}},
                 'replicas': [{'id': 'qwen25_a', 'model_key': 'qwen25', 'alias': runner.MODEL_ALIAS}]}
        self.assertEqual(len(runner.validate_endpoints(valid)), 1)
        for field, value in [('alias', 'qwen3.5-9b'), ('checkpoint', 'Qwen/Qwen3.5-9B'),
                             ('max_model_len', 8192)]:
            document = copy.deepcopy(valid)
            document['models']['qwen25'][field] = value
            with self.assertRaises(runner.WorkerStop):
                runner.validate_endpoints(document)


if __name__ == '__main__':
    unittest.main()
