from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from lfp_core import Atom, Fragment, Rule, sha256_text
from local_parser import CallStats
from run_phase2 import PublicCase, PublicSource
from run_phase4_baselines import LEAWindowResult
from run_phase5_graphpuct_xhub import (
    RealLLMGraphEnvironment,
    run_graphpuct_case,
)


class FakeXHubWindowParser:
    def __init__(self, public: PublicCase) -> None:
        self.public = public
        self.calls = 0

    def _fragment(self, source: PublicSource) -> Fragment:
        entity = "toy"
        if source.source_id == "s0":
            return Fragment(
                source.source_id,
                sha256_text(source.rendered_text),
                facts=(Atom("seed_ready", (entity,)),),
                validated=True,
                validation_note="fake-xhub-validator",
            )
        if source.source_id == "s1":
            return Fragment(
                source.source_id,
                sha256_text(source.rendered_text),
                rules=(Rule(
                    "r1",
                    Atom("bridge_ready", (entity,)),
                    (Atom("seed_ready", (entity,)),),
                    source.source_id,
                ),),
                validated=True,
                validation_note="fake-xhub-validator",
            )
        if source.source_id == "s2":
            return Fragment(
                source.source_id,
                sha256_text(source.rendered_text),
                rules=(Rule(
                    "r2",
                    Atom("review_released", (entity,)),
                    (Atom("bridge_ready", (entity,)),),
                    source.source_id,
                ),),
                validated=True,
                validation_note="fake-xhub-validator",
            )
        return Fragment(
            source.source_id,
            sha256_text(source.rendered_text),
            validated=True,
            validation_note="fake-xhub-validator",
        )

    def parse(self, *, sources, window_size):
        self.calls += 1
        fragments = {source.source_id: self._fragment(source) for source in sources}
        stats = CallStats(1, 100, 10, 0.1)
        return LEAWindowResult(
            window=tuple(source.source_id for source in sources),
            fragments=fragments,
            valid_sources=frozenset(fragments),
            errors={},
            cache_hit=False,
            cache_key=f"fake-{self.calls}",
            response_model_id="fake-xhub",
            new_stats=stats,
            recorded_stats=stats,
        )


@pytest.fixture()
def toy_case():
    sources = (
        PublicSource("s0", "seed_ready(toy)", "seed"),
        PublicSource("s1", "bridge_ready(toy) <- seed_ready(toy)", "bridge"),
        PublicSource("s2", "review_released(toy) <- bridge_ready(toy)", "witness"),
        PublicSource("s3", "unrelated legal carrier", "carrier"),
    )
    public = PublicCase(
        case_id="toy-product",
        carrier_size=4,
        condition="Productive",
        query=Atom("review_released", ("toy",)),
        query_text="is review released",
        sources=sources,
        source_order=tuple(source.source_id for source in sources),
        raw_public_sha256="toy-public-hash",
    )
    raw = {
        "case_id": public.case_id,
        "source_order": list(public.source_order),
        # Empty topology makes window_size=1 a true singleton policy for this
        # mechanics unit test. The real smoke uses the frozen directed SCC.
        "topology": {"edges": []},
    }
    return public, raw


def make_env(toy_case, *, logical_cap=20):
    public, raw = toy_case
    parser = FakeXHubWindowParser(public)
    env = RealLLMGraphEnvironment(
        public=public,
        raw_public=raw,
        parser=parser,
        window_size=1,
        real_window_cap=3,
        logical_eval_cap=logical_cap,
        unique_call_cap=4,
    )
    return env, parser


def test_search_entrypoint_has_no_sidecar_or_gold_parameter():
    parameters = inspect.signature(run_graphpuct_case).parameters
    assert "sidecar" not in parameters
    assert "gold" not in parameters


def test_discarded_branch_does_not_pollute_root(toy_case):
    env, _ = make_env(toy_case)
    root = env.root()
    s0 = env.action_map["w00"]
    s2 = env.action_map["w02"]
    simulated = env.step(root, s0, phase="simulation", branch_id="discard")
    committed = env.step(root, s2, phase="real", branch_id="root")
    assert Atom("seed_ready", ("toy",)) in simulated.closure
    assert Atom("seed_ready", ("toy",)) not in committed.closure
    assert committed.evaluated_window_ids == frozenset({"w02"})


def test_semantic_graph_state_merges_action_orders(toy_case):
    env, parser = make_env(toy_case)
    root = env.root()
    s0 = env.action_map["w00"]
    s1 = env.action_map["w01"]
    left = env.step(
        env.step(root, s0, phase="simulation", branch_id="left"),
        s1,
        phase="simulation",
        branch_id="left",
    )
    right = env.step(
        env.step(root, s1, phase="simulation", branch_id="right"),
        s0,
        phase="simulation",
        branch_id="right",
    )
    assert env.state_key(left) == env.state_key(right)
    assert parser.calls == 2
    assert env.accounting.logical_window_evaluations == 4
    assert env.accounting.run_memo_hits == 2


def test_real_graphpuct_closes_query_with_fake_xhub(toy_case):
    public, raw = toy_case
    parser = FakeXHubWindowParser(public)
    trial, state = run_graphpuct_case(
        public=public,
        raw_public=raw,
        parser=parser,
        window_size=1,
        real_window_cap=3,
        logical_eval_cap=24,
        unique_call_cap=4,
        simulation_transitions_per_move=8,
        simulations_per_move=4,
        rollout_depth=3,
        c_puct=1.35,
        seed=17,
    )
    assert trial["predicted_label"] == "Entailed"
    assert trial["proof_valid_on_model_kb"]
    assert public.query in state.closure
    assert trial["metrics"]["actual_xhub_usage"]["calls"] <= 4
    assert trial["metrics"]["logical_window_evaluations"] <= 24
    assert all(event["response_model_id"] == "fake-xhub" for event in trial["ledger"])
    assert all("validated_fragments" in event for event in trial["ledger"])
    assert all("unresolved_atoms" in event["feedback_after"] for event in trial["ledger"])


def test_logical_hard_cap_is_enforced(toy_case):
    env, _ = make_env(toy_case, logical_cap=1)
    root = env.root()
    env.step(root, env.action_map["w00"], phase="simulation", branch_id="one")
    with pytest.raises(RuntimeError, match="logical window-evaluation cap"):
        env.step(root, env.action_map["w01"], phase="simulation", branch_id="two")
