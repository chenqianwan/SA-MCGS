import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('test_science', HERE/'science/base_launcher.py')
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)
loader.import_science()
import methods_full as m


class Client:
    def __init__(self, cap):
        self.token_cap, self.used, self.reserve = cap, 0, 0
        self.phase, self.max_model_len = 'candidate', 131072
        self.prompts = []
    @property
    def token_usage(self):
        return {'accounted_tokens': self.used}
    @property
    def remaining_tokens(self):
        return self.token_cap-self.used-(0 if self.phase == 'selector' else self.reserve)
    def set_selector_reserve(self, value):
        self.reserve = value
    def set_phase(self, value):
        self.phase = value
    def estimate_request(self, prompt, **kwargs):
        return {'input_tokens': 50}
    async def call_json(self, prompt, **kwargs):
        self.prompts.append(prompt)
        self.used += 60
        assert self.used <= self.token_cap
        return {'candidate_id': 'C1'}


class MethodsTest(unittest.IsolatedAsyncioTestCase):
    async def test_candidates_are_independent_budgeted_and_blind(self):
        client = Client(2200)
        client.max_model_len = 307  # 50 prompt + 256 judge output fits without a second output reserve.
        scc = SimpleNamespace(clause_ids=['secret-real-id-a', 'secret-real-id-b'])
        graph = SimpleNamespace(clauses={i: SimpleNamespace(title='t', content='visible text',
                                    ground_truth='DO_NOT_LEAK') for i in scc.clause_ids}, edges=[])
        generated = []
        async def produce(*args):
            client.used += 200
            index = len(generated)+1
            result = {'ranking': [(i, .9) for i in scc.clause_ids],
                      'lea_risk_subgraph_nodes': [scc.clause_ids[index % 2]],
                      'hidden_evaluation': 'DO_NOT_LEAK', 'candidate_identity': index}
            generated.append(result)
            return result
        with tempfile.TemporaryDirectory() as temp, patch.object(m, 'candidate_lower_bound', return_value=200), \
                patch.object(m.cost, 'run_lea', side_effect=produce):
            result = await m.baseline(client, SimpleNamespace(), {}, graph, scc, 'lea', temp)
            self.assertGreater(len(generated), 1)
            self.assertEqual(len(generated), len(result['candidates']))
            self.assertLessEqual(client.used, client.token_cap)
            self.assertEqual(result['selection']['status'], 'judged')
            selected = result['selection']['selected_candidate_index']
            self.assertEqual(result['selected_result'], generated[selected-1])
            self.assertNotIn('DO_NOT_LEAK', client.prompts[0])
            self.assertNotIn('secret-real-id', client.prompts[0])
            self.assertEqual(len(list(Path(temp).glob('candidate_*.json'))), len(generated))

    async def test_no_valid_candidates_remains_failure(self):
        client = Client(600)
        scc = SimpleNamespace(clause_ids=['a', 'b'])
        graph = SimpleNamespace(clauses={i: SimpleNamespace(title='', content='x') for i in scc.clause_ids}, edges=[])
        async def produce(*args):
            client.used += 200
            raise ValueError('model schema failure')
        with tempfile.TemporaryDirectory() as temp, patch.object(m, 'candidate_lower_bound', return_value=200), \
                patch.object(m.cost, 'run_lea', side_effect=produce):
            result = await m.baseline(client, SimpleNamespace(), {}, graph, scc, 'lea', temp)
            self.assertIsNone(result['selected_result'])
            self.assertEqual(len(result['candidates']), 3)
            self.assertEqual(result['selection']['status'], 'no_valid_candidate')
            self.assertFalse(client.prompts)


if __name__ == '__main__':
    unittest.main()
