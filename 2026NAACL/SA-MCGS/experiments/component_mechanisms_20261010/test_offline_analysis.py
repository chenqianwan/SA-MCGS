"""Offline regression tests: size controls, prefix semantics, and denominators."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_analysis as a


class FakeBackend:
    hashes = {'fixture': 'not-experimental-data'}

    def __init__(self):
        self.ratios = []
        self.locked_capacities = []

    def identity(self, case, full):
        if full['scc_clause_ids'] != case['planned_scc_clause_ids']:
            raise ValueError('SCC identity mismatch')
        return {'physical_scc_uid': 'fixture-source'}

    def histories(self, full, ratio=None, capture_prefixes=None):
        if len(full['trace_events']) != 60:
            raise ValueError('Expected complete trace')
        self.ratios.append(ratio)
        ids = full['scc_clause_ids']
        histories = []
        for p in range(1, 61):
            shift = (p - 1) // 15
            if ratio is None:
                nodes = ids[shift:shift + 3]
            else:
                # Recomputed output is deliberately not a subset of the native
                # final core; truncating its old list would fail this fixture.
                k = min(len(ids), max(4, a.math.ceil(ratio * len(ids))))
                nodes = ids[-k:]
            histories.append({'evidence_risk_subgraph_nodes': nodes,
                              'ranking_by_risk': [(x, 1 - i / 10) for i, x in enumerate(ids)],
                              'evidence_subgraph_cap': len(nodes)})
        return histories, {}

    def aggregate(self, ids, trace):
        return {'ids': ids, 'prefix': len(trace)}

    def select(self, ids, stats, k, selector):
        return list(ids[:k]) if selector == 'mean-risk-matched-k' else list(ids[-k:]) if k else []

    def locked(self, histories, ids, k):
        self.locked_capacities.append((len(histories), k))
        selected = []
        for h in histories:
            for x in h['evidence_risk_subgraph_nodes']:
                if len(selected) < k and x not in selected:
                    selected.append(x)
        return [x for x in ids if x in selected]


def fixture(uid='case-one'):
    ids = list('abcdefghij')
    injection = {'risk_nodes': ['a', 'b'], 'evidence_nodes': ['a', 'b'],
                 'root_node': 'a', 'witness_node': 'b', 'bridge_node': 'c'}
    case = {'case_uid': uid, 'case_id': uid, 'case_order': 1, 'domain': 'cuad',
            'template': 'condition_trigger', 'scc_size': 10,
            'planned_scc_clause_ids': ids, 'planned_injection_identity': injection}
    full = {'model': 'llama-3.1-8b', 'scc_clause_ids': ids,
            'trace_events': [{'completion_index': i} for i in range(1, 61)]}
    return case, full


class OfflineAnalysisTest(unittest.TestCase):
    def test_common_search_rule_ignores_native_output_size(self):
        case, full = fixture()
        rows = a.analyze_case(full, case, 'llama', 'no_both', FakeBackend())
        self.assertEqual(len(rows), 8)
        for prefix in a.PREFIXES:
            selected = {r['selector']: r for r in rows if r['prefix'] == prefix}
            self.assertEqual(selected['common-mean-risk']['output_k'], 5)
            self.assertEqual(selected['native-core']['output_k'], 3)

    def test_cap_recomputes_and_matches_actual_full_k(self):
        case, full = fixture()
        backend = FakeBackend()
        rows = a.analyze_case(full, case, 'llama', 'full', backend)
        self.assertEqual(len(rows), 40)
        self.assertEqual(backend.ratios, [None, .25, .35, .45, .60])
        for ratio in a.CAP_RATIOS:
            group = [r for r in rows if r['analysis'] == 'cap' and r['cap_ratio'] == ratio]
            self.assertEqual(len({r['output_k'] for r in group}), 1)
            self.assertEqual(len({r['root_at_3'] for r in group}), 1)
            native = next(r for r in group if r['selector'] == 'full')
            self.assertIn('j', native['selected_nodes'])
            self.assertEqual(native['output_k'], max(4, a.math.ceil(ratio * 10)))

    def test_locked_replays_from_first_prefix_with_one_terminal_capacity(self):
        case, full = fixture()
        backend = FakeBackend()
        rows = a.analyze_case(full, case, 'llama', 'full', backend)
        native = next(r for r in rows if r['analysis'] == 'selector' and r['prefix'] == 60 and r['selector'] == 'full')
        locked = next(r for r in rows if r['analysis'] == 'selector' and r['prefix'] == 60 and r['selector'] == 'locked-matched-k')
        self.assertEqual(native['selected_nodes'], ['d', 'e', 'f'])
        self.assertEqual(locked['selected_nodes'], ['a', 'b', 'c'])
        self.assertEqual(native['output_k'], locked['output_k'])
        self.assertIn((60, 3), backend.locked_capacities)

    def test_ground_truth_only_changes_metrics(self):
        case, full = fixture()
        before = a.analyze_case(full, case, 'llama', 'full', FakeBackend())
        changed = copy.deepcopy(case)
        changed['planned_injection_identity'].update(root_node='h', witness_node='i', bridge_node='j', risk_nodes=['h', 'i'])
        after = a.analyze_case(full, changed, 'llama', 'full', FakeBackend())
        self.assertEqual([r['selected_nodes'] for r in before], [r['selected_nodes'] for r in after])
        self.assertNotEqual(before[0]['risk_all'], after[0]['risk_all'])

    def test_failure_zero_pending_not_failure_and_compression_valid_only(self):
        case, full = fixture()
        rows = a.analyze_case(full, case, 'llama', 'full', FakeBackend(), quick=True)
        failed, _ = fixture('case-failed')
        pending, _ = fixture('case-pending')
        rows += a.unavailable_rows(failed, 'llama', 'full', 'scientific_failure', quick=True)
        rows += a.unavailable_rows(pending, 'llama', 'full', 'pending', quick=True)
        summary = next(r for r in a.summarize(rows) if r['grouping'] == 'all' and r['selector'] == 'common-mean-risk')
        self.assertEqual((summary['planned'], summary['terminal'], summary['scientific_failures'], summary['pending']), (3, 2, 1, 1))
        self.assertIsNone(summary['risk_all'])
        self.assertEqual(summary['risk_all_terminal_rate'], .5)
        self.assertEqual(summary['risk_all_planned_lower_bound'], 1 / 3)
        self.assertEqual(summary['compression_valid_n'], 1)
        self.assertEqual(summary['compression_valid_mean'], .5)
        done = [r for r in rows if r['case_uid'] != 'case-pending']
        strict = next(r for r in a.summarize(done) if r['grouping'] == 'all' and r['selector'] == 'common-mean-risk')
        self.assertEqual(strict['risk_all'], .5)

    def test_no_bridge_is_ineligible_not_negative(self):
        case, full = fixture()
        case['planned_injection_identity']['bridge_node'] = None
        rows = a.analyze_case(full, case, 'llama', 'full', FakeBackend(), quick=True)
        self.assertIsNone(rows[0]['bridge_retained'])
        group = next(r for r in a.summarize(rows) if r['grouping'] == 'all')
        self.assertEqual(group['bridge_retained_n'], 0)
        self.assertIsNone(group['bridge_retained'])

    def test_infrastructure_failure_is_not_algorithm_zero(self):
        case, full = fixture()
        rows = a.analyze_case(full, case, 'llama', 'full', FakeBackend(), quick=True)
        other, _ = fixture('infra-failed')
        rows += a.unavailable_rows(other, 'llama', 'full', 'infrastructure_failure', quick=True)
        group = next(r for r in a.summarize(rows) if r['grouping'] == 'all' and r['selector'] == 'common-mean-risk')
        self.assertEqual(group['terminal'], 2)
        self.assertEqual(group['evaluable_terminal'], 1)
        self.assertEqual(group['infrastructure_failures'], 1)
        self.assertEqual(group['scientific_failures'], 0)
        self.assertIsNone(group['risk_all'])
        self.assertEqual(group['risk_all_terminal_rate'], 1)
        self.assertEqual(group['risk_all_planned_lower_bound'], .5)

    def test_runner_io_and_protocol_pollution(self):
        case, full = fixture()
        other, _ = fixture('second')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'frozen_case_plan.json').write_text(json.dumps([case, other]))
            protocol = {'version': 1}
            (root / 'protocol.json').write_text(json.dumps(protocol))
            target = root / 'results/llama/case-one/full/final.json'
            target.parent.mkdir(parents=True)
            record = {'case_uid': case['case_uid'], 'case_id': case['case_id'], 'domain': case['domain'],
                      'arm': 'full', 'model': 'llama', 'model_alias': full['model'], 'seed': 42,
                      'repeat_index': 1, 'status': 'complete', 'completion_status': 'complete',
                      'protocol_sha256': a.file_sha(root / 'protocol.json'), 'result': full, 'metrics': {'valid': True}}
            target.write_text(json.dumps(record))
            summary = a.analyze_run(root, root / 'reports', backend=FakeBackend(), models=['llama'],
                                    arms=['full'], expected_cases=2, quick=True)
            self.assertFalse(summary['complete'])
            self.assertEqual(summary['counts']['pending'], 1)
            self.assertEqual(summary['counts']['scientific_failures'], 0)
            record['protocol_sha256'] = 'f' * 64
            target.write_text(json.dumps(record))
            corrupted = a.analyze_run(root, root / 'reports', backend=FakeBackend(), models=['llama'],
                                     arms=['full'], expected_cases=2, quick=True)
            self.assertEqual(corrupted['counts']['analysis_errors'], 1)
            self.assertEqual(corrupted['counts']['scientific_failures'], 0)

    def test_outside_nodes_rejected(self):
        case, full = fixture()
        with self.assertRaises(ValueError):
            a.score_nodes(full['scc_clause_ids'], ['outside'], ['a'], case['planned_injection_identity'])


if __name__ == '__main__':
    unittest.main()
