"""Regression tests for the V3 synthetic SCC-scaling diagnostic.

These tests protect the semantic boundary of the A0 experiment.  They do not
turn the synthetic benchmark into confirmatory evidence.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = load_module("v3_generator", "generate_benchmark.py")
runner = load_module("v3_a0_runner", "run_a0_scc_scaling.py")


@pytest.fixture(scope="module")
def cases():
    loaded = runner.load_cases(ROOT / "data" / "benchmark.jsonl")
    assert len(loaded) == 420
    return loaded


def family(cases, size: int, family_id: str = "f00"):
    prefix = f"v3-s{size:02d}{family_id}"
    selected = [case for case in cases if case.family_id == prefix]
    assert len(selected) == 3
    return {case.condition: case for case in selected}


@pytest.mark.parametrize("size", [3, 5, 7, 9, 12, 16, 20])
def test_seeded_unseeded_and_matched_dag_semantics(cases, size):
    triplet = family(cases, size)
    seeded = triplet["productive_seeded_scc"]
    unseeded = triplet["unseeded_scc"]
    dag = triplet["matched_dag"]

    assert seeded.label == dag.label == "entailed"
    assert unseeded.label == "unknown"
    assert seeded.actual_recursive_scc_size == size
    assert unseeded.actual_recursive_scc_size == size
    assert dag.actual_recursive_scc_size == 0

    seeded_env = runner.OracleNavigationEnvironment(seeded, "canonical")
    unseeded_env = runner.OracleNavigationEnvironment(unseeded, "canonical")
    dag_env = runner.OracleNavigationEnvironment(dag, "canonical")
    assert seeded_env.oracle_entails
    assert dag_env.oracle_entails
    assert not unseeded_env.oracle_entails

    # The exact proof route is reachable with one unit of slack in every tier.
    assert runner.reference_proof_action_cost(seeded) == 2 * size + 1
    assert runner.reference_proof_action_cost(dag) == 2 * size + 1
    assert seeded.action_budget == dag.action_budget == 2 * size + 2
    assert runner.reference_proof_action_cost(unseeded) is None


@pytest.mark.parametrize("size", [3, 9, 20])
def test_every_gold_proof_source_is_source_deletion_causal(cases, size):
    for condition in ("productive_seeded_scc", "matched_dag"):
        case = family(cases, size)[condition]
        proof_sources = set(case.generator_gold["proof_source_ids"])
        assert proof_sources
        for removed in proof_sources:
            facts = []
            rules = []
            for source in case.sources:
                if source.source_id != removed:
                    facts.extend(source.facts)
                    rules.extend(source.rules)
            assert case.query not in runner.positive_horn_closure(facts, rules)


def test_canonical_one_way_ring_has_no_small_exact_transposition(cases):
    """The native graph's lack of merge opportunity is a recorded NO-GO."""

    case = family(cases, 9)["productive_seeded_scc"]
    for merge in (False, True):
        search = runner.PairedMonteCarloSearch(
            environment=runner.OracleNavigationEnvironment(case, "canonical"),
            seed=17,
            transition_cap=512,
            exploration_constant=1.35,
            merge_states=merge,
        )
        result = search.run()
        if merge:
            assert result["tt_hits"] == 0
        else:
            assert result["duplicate_nodes"] == 0


def test_overlay_creates_only_strict_decision_equivalent_merges(cases):
    case = family(cases, 5)["productive_seeded_scc"]
    search = runner.PairedMonteCarloSearch(
        environment=runner.OracleNavigationEnvironment(
            case, "bidirectional_chorded_core_overlay"
        ),
        seed=17,
        transition_cap=2048,
        exploration_constant=1.35,
        merge_states=True,
    )
    result = search.run()
    assert result["tt_hits"] > 0
    assert result["nodes"] == result["distinct_state_keys"]
    for node in search.nodes.values():
        assert tuple(search.env.actions(node.state)) == tuple(search.env.actions(node.state))


def test_state_key_rejects_same_closure_with_different_budget_or_location(cases):
    case = family(cases, 3)["productive_seeded_scc"]
    env = runner.OracleNavigationEnvironment(case, "canonical")
    root = env.root()
    different_budget = env.make_state(root.current_node, root.acquired_mask, root.remaining_budget - 1)
    neighbor = env.adjacency[root.current_node][0]
    different_location = env.make_state(neighbor, root.acquired_mask, root.remaining_budget)
    assert root.closure == different_budget.closure == different_location.closure
    assert root.key != different_budget.key
    assert root.key != different_location.key
