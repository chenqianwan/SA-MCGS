import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner


class QueueTests(unittest.TestCase):
    def test_simultaneous_workers_cannot_claim_same_arm(self):
        case = {'case_uid': 'same-case', 'main_case_order': 1}
        tasks = [(case, 'lea'), (case, 'full-scc')]
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, 'ROOT', Path(directory)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                claims = list(pool.map(lambda _: runner.claim_next(tasks, 'kimi'), range(2)))
            self.assertEqual({claim[1] for claim in claims}, {'lea', 'full-scc'})
            self.assertIsNone(runner.claim_next(tasks, 'kimi'))
            for claimed_case, method, lock in claims:
                final = Path(directory)/'results/kimi'/claimed_case['case_uid']/method/'final.json'
                final.parent.mkdir(parents=True)
                final.write_text('{}')
                lock.close()
            self.assertIsNone(runner.claim_next(tasks, 'kimi'))

    def test_real_full_queue_has_480_unique_arms_and_largest_budget_first(self):
        plan = runner.read(runner.ROOT/'science/repo/portable_data/qwen80_case_plan.json')
        runner.load_scope(plan)
        refs = runner.historical_reference(plan)
        keys = set()
        for model in runner.MODEL_KEYS:
            tasks = runner.ordered_tasks(plan, refs, model)
            budgets = [refs[(model, case['case_uid'])]['usage']['total_tokens'] for case, _ in tasks]
            self.assertEqual(budgets, sorted(budgets, reverse=True))
            self.assertEqual(len(tasks), 160)
            keys.update((model, c['case_uid'], method) for c, method in tasks)
            self.assertNotIn('sa-mcgs', {method for _, method in tasks})
        self.assertEqual(len(keys), 480)


if __name__ == '__main__':
    unittest.main()
