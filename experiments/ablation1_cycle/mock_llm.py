"""Mock LLM client for Ablation 1 experiments.

Simulates realistic LLM behavior: noisy, context-dependent evaluation.
The key insight: in real LLM evaluation, a node's score depends on
what OTHER nodes are co-evaluated (context window). This makes cycles
problematic because the same node gets evaluated with different contexts
as the search traverses different paths through the cycle.
"""
from __future__ import annotations

import hashlib
import random

from experiments.ablation1_cycle.graph_generator import SyntheticGraph


class MockEvaluator:
    """Simulates LLM evaluation with context-dependent scoring + noise.

    Context dependency: A node's score is influenced by its co-evaluated
    neighbors. In a cycle A->B->C->A, evaluating {A,B} gives different
    scores than evaluating {A,C}. This is realistic: LLMs give different
    assessments depending on what other clauses are shown.
    """

    def __init__(
        self,
        graph: SyntheticGraph,
        noise_std: float = 0.08,
        context_influence: float = 0.15,
    ):
        self.graph = graph
        self.noise_std = noise_std
        self.context_influence = context_influence

    def evaluate_window(self, window: list[str]) -> dict[str, float]:
        """Return risk scores influenced by context (other nodes in window)."""
        results = {}
        window_set = set(window)

        for nid in window:
            node = self.graph.nodes.get(nid)
            if node is None:
                results[nid] = 0.5
                continue

            base_score = node.ground_truth_risk

            # Context influence: average risk of co-evaluated nodes shifts score
            context_scores = []
            for other_id in window:
                if other_id != nid:
                    other_node = self.graph.nodes.get(other_id)
                    if other_node:
                        context_scores.append(other_node.ground_truth_risk)

            if context_scores:
                context_mean = sum(context_scores) / len(context_scores)
                # Context pulls score toward the window's average
                context_shift = (context_mean - base_score) * self.context_influence
            else:
                context_shift = 0.0

            # Window-composition-dependent hash noise (deterministic per window combo)
            # This ensures same window always gives same result (simulating TT benefit)
            # but different windows give different results
            window_key = "|".join(sorted(window)) + "|" + nid
            hash_val = int(hashlib.md5(window_key.encode()).hexdigest()[:8], 16)
            hash_noise = ((hash_val % 1000) / 1000.0 - 0.5) * 0.1

            # Random noise (simulates LLM stochasticity)
            random_noise = random.gauss(0, self.noise_std) if self.noise_std > 0 else 0.0

            score = base_score + context_shift + hash_noise + random_noise
            score = max(0.0, min(1.0, score))
            results[nid] = score

        return results
