import unittest
from types import SimpleNamespace

from rescore_strict_failures import evaluate, original_id_helpers


class MetricwiseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = original_id_helpers()
        cls.case = {'planned_scc_clause_ids': ['A', 'B', 'C', 'D'],
                    'planned_injection_identity': {'root_node': 'D', 'risk_nodes': ['C', 'D']}}
        cls.clauses = {x: SimpleNamespace(title='Title ' + x) for x in 'ABCD'}

    def score(self, text):
        return evaluate(text, self.case, self.clauses, self.helpers)

    def test_incomplete_ranking_is_not_backfilled(self):
        result = self.score('{"global_ranking":["B"],"risk_subgraph_nodes":["C","D"]}')
        self.assertEqual(result['observed_ranking'], ['B'])
        self.assertEqual(result['metrics'], {'root_at3': 0, 'risk_any': 1, 'risk_all': 1, 'compression': .5})

    def test_complete_entries_in_truncated_rank(self):
        result = self.score('{"global_ranking":[{"id":"D","rank":1},{"id":"C","rank":2},{"id":"A","rank":')
        self.assertEqual(result['observed_ranking'], ['D', 'C'])
        self.assertEqual(result['metrics'], {'root_at3': 1, 'risk_any': 0, 'risk_all': 0, 'compression': 0})

    def test_partial_risk_never_claims_compression(self):
        result = self.score('{"risk_subgraph_nodes":["D","C","unfin')
        self.assertEqual(result['metrics'], {'root_at3': 0, 'risk_any': 1, 'risk_all': 1, 'compression': 0})
        self.assertFalse(result['available']['compression'])

    def test_explicit_rank_and_duplicate_policy(self):
        result = self.score('{"global_ranking":[{"id":"A","rank":4},{"id":"B","rank":3},{"id":"C","rank":2},{"id":"D","rank":1},{"id":"D","rank":0}]}')
        self.assertEqual(result['observed_ranking'], ['D', 'C', 'B', 'A'])
        self.assertEqual(result['ranking_duplicates'], ['D'])

    def test_flat_marker_segment(self):
        result = self.score('{"risk_factor_distribution":[{},"global_ranking",{"id":"D","rank":1},"risk_subgraph_nodes","C","D"]}')
        self.assertEqual(result['metrics'], {'root_at3': 1, 'risk_any': 1, 'risk_all': 1, 'compression': .5})
        self.assertEqual(result['risk_recovery_method'], 'marker_array')

    def test_marker_with_single_array(self):
        result = self.score('{"global_ranking":["A","D","risk_subgraph_nodes",["C","D"],"risk_subgraph_rationale","text"]}')
        self.assertEqual(result['metrics']['compression'], .5)
        self.assertEqual(result['observed_risk_nodes'], ['C', 'D'])

    def test_duplicate_field_does_not_choose_better_value(self):
        result = self.score('{"global_ranking":["D"],"global_ranking":["A"],"risk_subgraph_nodes":["C"]}')
        self.assertEqual(result['observed_ranking'], [])
        self.assertEqual(result['metrics']['root_at3'], 0)

    def test_empty_or_absent_risk_is_zero_not_perfect_compression(self):
        for text in ['{}', '{"risk_subgraph_nodes":[]}', '{"risk_subgraph_nodes":["unknown"]}']:
            self.assertEqual(self.score(text)['metrics'], {m: 0 for m in ('root_at3', 'risk_any', 'risk_all', 'compression')})


if __name__ == '__main__':
    unittest.main()
