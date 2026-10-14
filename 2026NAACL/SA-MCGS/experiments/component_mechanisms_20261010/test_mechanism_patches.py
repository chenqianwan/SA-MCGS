"""Offline intervention and async metadata tests; never constructs an SDK."""
from __future__ import annotations

import asyncio
from collections import Counter
import copy
import json
import random
import unittest

from mechanism_patches import ARMS, MechanismMCGS, derive_search_seed
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.models.clause import Clause
from src.models.graph import DependencyGraph, Edge, SCCInfo


def config(concurrency=1, budget=24):
    return {"alphago_mcgs": {
        "budget": budget, "window_size": 4, "concurrency": concurrency,
        "trace": True, "temperature": 0.4, "max_tokens": 2048,
        "tt_max_reuse": 3,
        "evidence": {"relation_first": True, "relation_prior_weight": 0.85,
                     "probe_fraction": 0.30, "critical_pair_ledger": True,
                     "critical_pair_revisit_fraction": 0.45},
    }, "detection": {"alpha": 0.1, "min_rollouts": 6}}


def fixture():
    ids = [f"n{i}" for i in range(8)]
    edges = [Edge(source=node, target=ids[(i+1) % len(ids)])
             for i, node in enumerate(ids)]
    graph = DependencyGraph(clauses={node: Clause(id=node, title=node, content=node)
                                    for node in ids}, edges=edges)
    return graph, SCCInfo(id="mock", clause_ids=ids, size=len(ids))


class MockLLM:
    def __init__(self, delays=False):
        self.calls = 0
        self.delays = delays

    async def call_json(self, prompt, **kwargs):
        self.calls += 1
        window = json.loads(prompt)
        if self.delays:
            await asyncio.sleep((4-self.calls % 4) * 0.001)
        pair = {"source": window[0], "target": window[1],
                "reason": "severe same-path incompatible constraints with no fallback",
                "same_path_score": 1.0, "severity_score": 1.0,
                "mutual_incompatibility_score": 1.0, "no_fallback": True}
        return {"clause_evaluations": {
            node: {"risk_score": (int(node[1:])+1)/10, "reasoning": "mock"}
            for node in window}, "local_risk_subgraph_nodes": window[:2],
            "repair_entry_nodes": window[:1], "local_conflict_edges": [pair],
            "critical_pairs": [pair], "conflicts": [
                {"clause_a": window[0], "clause_b": window[1],
                 "description": pair["reason"]}]}


def setup_engine(cls=MechanismMCGS, *, arm="full", seed=31415, concurrency=1,
                 budget=24, delays=False, callback=None):
    llm = MockLLM(delays)
    kwargs = {} if cls is AlphaGoMCGS else {
        "arm": arm, "seed": seed, "trace_callback": callback}
    engine = cls(llm_client=llm, config=config(concurrency, budget), **kwargs)
    engine._build_focused_prompt = json.dumps
    return engine, llm


def semantic(result):
    return {key: value for key, value in result.items()
            if key not in {"elapsed_seconds", "elapsed", "time", "mechanism_audit"}}


class MechanismTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_serial_matches_original_bytecode_and_mock_responses(self):
        graph, scc = fixture()
        original, _ = setup_engine(AlphaGoMCGS)
        state = random.getstate()
        try:
            random.seed(31415)
            expected = await original.search(graph, scc)
        finally:
            random.setstate(state)
        patched, _ = setup_engine()
        actual = await patched.search(graph, scc)
        self.assertEqual(semantic(expected), semantic(actual))

    async def test_full_parallel_metadata_matches_selected_iteration(self):
        graph, scc = fixture()
        snapshots = []
        engine, _ = setup_engine(concurrency=4, budget=32, delays=True,
                                 callback=snapshots.append)
        result = await engine.search(graph, scc)
        selected = {row["iteration"]: row for row in engine._selection_events}
        self.assertEqual(len(result["trace_events"]), 32)
        self.assertEqual(len(snapshots), 32)
        self.assertNotEqual([r["iteration"] for r in snapshots], list(range(1, 33)))
        for event in snapshots:
            expected = selected[event["iteration"]]
            self.assertEqual(event["window"], expected["window"])
            for key in set(expected)-{"iteration", "window"}:
                self.assertEqual(event["selection"].get(key), expected[key])
        revisits = Counter()
        for event in snapshots:
            meta = event['selection']
            if meta['mode'] != 'critical_pair_revisit':
                continue
            pair = tuple(sorted((meta['source'], meta['target'])))
            reported = {tuple(sorted((edge['source'], edge['target'])))
                        for edge in event['local_conflict_edges']}
            if pair in reported:
                revisits[pair] += 1
        self.assertGreater(sum(revisits.values()), 0)
        for pair, row in engine._critical_pair_ledger.items():
            self.assertEqual(row['revisit_count'], revisits[pair])
        snapshots[0]["selection"]["mode"] = "tampered"
        self.assertNotEqual(result["trace_events"][0]["selection"]["mode"], "tampered")

    async def test_rng_is_instance_local_even_with_interleaved_searches(self):
        graph, scc = fixture()
        state = random.getstate()
        for arm in ('full', 'random_windows'):
            first, _ = setup_engine(arm=arm, seed=7, delays=True)
            second, _ = setup_engine(arm=arm, seed=8, delays=True)
            actual, _ = await asyncio.gather(first.search(graph, scc), second.search(graph, scc))
            reference, _ = setup_engine(arm=arm, seed=7, delays=True)
            expected = await reference.search(graph, scc)
            self.assertEqual(semantic(actual), semantic(expected))
        self.assertEqual(random.getstate(), state)

    async def test_all_arms_keep_ledger_and_native_core(self):
        graph, scc = fixture()
        for arm in ARMS:
            engine, _ = setup_engine(arm=arm, concurrency=4, delays=True)
            result = await engine.search(graph, scc)
            self.assertTrue(engine.critical_pair_ledger_enabled)
            self.assertTrue(result["critical_pair_ledger_rows"])
            self.assertIs(engine._select_dynamic_core_subgraph.__func__,
                          AlphaGoMCGS._select_dynamic_core_subgraph)
            self.assertTrue(result["mechanism_audit"]["completed_trace_metadata_verified"])

    async def test_infrastructure_baseexception_propagates(self):
        class Stop(BaseException):
            pass
        graph, scc = fixture()
        engine, _ = setup_engine(concurrency=1)
        async def fail(*args, **kwargs):
            raise Stop("stop")
        engine.llm.call_json = fail
        with self.assertRaises(Stop):
            await engine.search(graph, scc)
        self.assertFalse(engine._search_active)

    def test_guidance_gates_preserve_critical_cadence(self):
        graph, scc = fixture()
        observations = {}
        for arm in ARMS[:-1]:
            engine, _ = setup_engine(arm=arm)
            engine._init_state(graph, scc)
            engine._update_critical_pair_ledger("n0", "n1", ["severe no fallback conflict"],
                explicit_count=1, local_count=1, iteration=1,
                edge_features={"same_path_score": 1, "severity_score": 1,
                               "mutual_incompatibility_score": 1, "no_fallback": True})
            engine._update_critical_pair_ledger("n0", "n1", ["severe no fallback conflict"],
                explicit_count=1, local_count=1, iteration=2,
                edge_features={"same_path_score": 1, "severity_score": 1,
                               "mutual_incompatibility_score": 1, "no_fallback": True})
            engine._local_conflict_pair_counts[('n0', 'n1')] = 4
            engine._local_conflict_pair_reasons[('n0', 'n1')] = ["severe no fallback conflict"]
            modes = []
            for iteration in range(24):
                window = engine._select_relation_probe_window(iteration)
                modes.append(engine._last_selection_meta.get("mode") if window else None)
            observations[arm] = modes
            if arm in {"no_relation_guidance", "no_both"}:
                self.assertEqual(engine._progressive_relation_bias(1.0, 3), 0)
                self.assertNotIn("relation_probe", modes)
        full = observations['full']
        no_relation = observations['no_relation_guidance']
        self.assertIn('critical_pair_revisit', full)
        self.assertEqual([i for i,m in enumerate(full) if m=='critical_pair_revisit'],
                         [i for i,m in enumerate(no_relation) if m=='critical_pair_revisit'])
        self.assertNotIn('critical_pair_revisit', observations['no_critical_revisit'])
        self.assertEqual(observations['no_both'], [None]*24)

    def test_config_not_mutated_and_seed_derivation_stable(self):
        original = config()
        before = copy.deepcopy(original)
        MechanismMCGS(None, original, arm='no_both', seed=5)
        self.assertEqual(original, before)
        self.assertEqual(derive_search_seed(42, 'case'), derive_search_seed(42, 'case'))
        self.assertNotEqual(derive_search_seed(42, 'case'), derive_search_seed(42, 'other'))
        with self.assertRaises(ValueError):
            MechanismMCGS(None, config(), arm='bad', seed=1)


if __name__ == '__main__':
    unittest.main()
