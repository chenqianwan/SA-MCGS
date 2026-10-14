#!/usr/bin/env python3
"""Real-LLM GraphPUCT + exact-LFP end-to-end smoke.

This runner is deliberately separate from the frozen Phase-3 oracle smoke and
the Phase-4 baselines.  Search receives only the public query, sources and
topology.  A window outcome is produced by the XHub model, passed through the
strict source-grounded validator, committed to a branch-local KB, and closed
with the exact positive-Horn engine before the next PUCT decision.

The evaluator sidecar is loaded only after every search run has completed.
It is never passed to the environment, action prior, rollout, value function,
state key, or parser.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from dotenv import load_dotenv

from lfp_core import (
    Atom,
    CommittedKB,
    ExecutionReceipt,
    Fragment,
    LFPResult,
    least_fixed_point,
    sha256_text,
    source_set_sufficient,
    verify_proof,
)
from local_parser import CallStats, OpenAICompatibleClient
from run_phase2 import (
    DEFAULT_GOLD,
    DEFAULT_PUBLIC,
    EvaluatorSidecar,
    PublicCase,
    PublicSource,
    _public_case,
    _sidecar,
    gold_fragment,
    read_jsonl,
    write_json,
    write_jsonl,
)
from run_phase4_baselines import (
    DEFAULT_XHUB_BASE_URL,
    DEFAULT_XHUB_MODEL,
    JSON_REQUEST_PROTOCOL,
    LEA_SCHEMA,
    LEA_SYSTEM,
    LEA_VALIDATOR_VERSION,
    LEAWindowParser,
    _merge_source_fragments,
    deduplicate_window_sets,
    deterministic_windows,
)


SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parent
DEFAULT_RESULTS = ROOT / "results" / "phase5_graphpuct_xhub_smoke"
SCHEMA_VERSION = "bgb-phase5-real-graphpuct-xhub-lfp-v1"
EVIDENCE_STATUS = "exploratory_real_llm_end_to_end_smoke"
CLAIM_BOUNDARY = (
    "Two controlled size-9 cases test whether the real XHub parser can sit "
    "inside GraphPUCT and feed exact LFP online. This is an end-to-end "
    "mechanism smoke, not a compute-matched comparison, a natural-data "
    "generalization result, or an algorithmic-advantage claim."
)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_stats(left: CallStats, right: CallStats) -> CallStats:
    return left + right


def stats_from_dict(raw: Mapping[str, Any]) -> CallStats:
    return CallStats(
        int(raw.get("calls", 0)),
        int(raw.get("prompt_tokens", 0)),
        int(raw.get("completion_tokens", 0)),
        float(raw.get("latency_seconds", 0.0)),
    )


def _tokens(text: str) -> frozenset[str]:
    return frozenset(item.lower() for item in TOKEN_PATTERN.findall(text))


@dataclass(frozen=True, order=True)
class WindowAction:
    action_id: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class BranchState:
    evaluated_window_ids: frozenset[str]
    fragments: tuple[Fragment, ...]
    closure: frozenset[Atom]
    proof_source_ids: tuple[str, ...]
    lfp_iterations: int
    remaining_commits: int


@dataclass(frozen=True)
class WindowObservation:
    action: WindowAction
    fragments: tuple[Fragment, ...]
    valid_source_ids: tuple[str, ...]
    errors: tuple[tuple[str, str], ...]
    response_model_id: str | None
    parser_cache_hit: bool
    parser_cache_key: str
    new_stats: CallStats
    recorded_stats: CallStats


@dataclass
class SearchAccounting:
    logical_window_evaluations: int = 0
    unique_window_observations: int = 0
    run_memo_hits: int = 0
    parser_cache_hits: int = 0
    actual_usage: CallStats = field(default_factory=CallStats)
    logical_replay_usage: CallStats = field(default_factory=CallStats)
    events: list[dict[str, Any]] = field(default_factory=list)


def _window_actions(raw_public: Mapping[str, Any], window_size: int) -> tuple[WindowAction, ...]:
    windows = deduplicate_window_sets(deterministic_windows(raw_public, window_size))
    return tuple(
        WindowAction(f"w{index:02d}", tuple(window))
        for index, window in enumerate(windows)
    )


def _kb_from_fragments(fragments: Iterable[Fragment]) -> CommittedKB:
    kb = CommittedKB()
    for sequence, fragment in enumerate(
        sorted(fragments, key=lambda item: item.source_id), 1
    ):
        kb = kb.commit(
            ExecutionReceipt(
                fragment.source_id,
                fragment.source_text_sha256,
                sequence,
                executed=True,
            ),
            fragment,
        )
    return kb


def _state_from_fragments(
    public: PublicCase,
    *,
    evaluated_window_ids: Iterable[str],
    fragments: Iterable[Fragment],
    remaining_commits: int,
) -> BranchState:
    ordered = tuple(sorted(fragments, key=lambda item: item.source_id))
    kb = _kb_from_fragments(ordered)
    lfp = least_fixed_point(kb)
    proof = lfp.proof(public.query)
    return BranchState(
        evaluated_window_ids=frozenset(evaluated_window_ids),
        fragments=ordered,
        closure=lfp.closure,
        proof_source_ids=proof.source_ids if proof else tuple(),
        lfp_iterations=lfp.iterations,
        remaining_commits=remaining_commits,
    )


def _merge_state_fragments(
    public: PublicCase,
    existing: Sequence[Fragment],
    observed: Sequence[Fragment],
) -> tuple[Fragment, ...]:
    grouped: dict[str, list[Fragment]] = defaultdict(list)
    for fragment in (*existing, *observed):
        if not fragment.validated:
            raise ValueError("fail-closed: an unvalidated fragment reached state merge")
        if fragment.source_id not in public.source_map:
            raise ValueError("fragment references a source outside the public case")
        grouped[fragment.source_id].append(fragment)
    return tuple(
        _merge_source_fragments(public.source_map[source_id], grouped[source_id])
        for source_id in sorted(grouped)
    )


class RealLLMGraphEnvironment:
    """Public-only graph-window environment with real, memoized model outcomes."""

    def __init__(
        self,
        *,
        public: PublicCase,
        raw_public: Mapping[str, Any],
        parser: LEAWindowParser,
        window_size: int,
        real_window_cap: int,
        logical_eval_cap: int,
        unique_call_cap: int,
    ) -> None:
        self.public = public
        self.raw_public = raw_public
        self.parser = parser
        self.window_size = window_size
        self.real_window_cap = real_window_cap
        self.logical_eval_cap = logical_eval_cap
        self.unique_call_cap = unique_call_cap
        self.window_actions = _window_actions(raw_public, window_size)
        self.action_map = {action.action_id: action for action in self.window_actions}
        self.observation_memo: dict[str, WindowObservation] = {}
        self.accounting = SearchAccounting()

    def root(self) -> BranchState:
        return _state_from_fragments(
            self.public,
            evaluated_window_ids=(),
            fragments=(),
            remaining_commits=self.real_window_cap,
        )

    def proved(self, state: BranchState) -> bool:
        return self.public.query in state.closure

    def actions(self, state: BranchState) -> tuple[WindowAction, ...]:
        if state.remaining_commits <= 0 or self.proved(state):
            return tuple()
        return tuple(
            action
            for action in self.window_actions
            if action.action_id not in state.evaluated_window_ids
        )

    def state_key(self, state: BranchState) -> tuple[Any, ...]:
        semantic_program = tuple(
            (
                fragment.source_id,
                tuple(str(atom) for atom in fragment.facts),
                tuple(rule.signature for rule in fragment.rules),
            )
            for fragment in state.fragments
        )
        return (
            tuple(sorted(state.evaluated_window_ids)),
            semantic_program,
            tuple(str(atom) for atom in sorted(state.closure)),
            state.proof_source_ids,
            state.remaining_commits,
            tuple(action.action_id for action in self.actions(state)),
        )

    def remaining_logical(self) -> int:
        return self.logical_eval_cap - self.accounting.logical_window_evaluations

    def feedback(self, state: BranchState) -> dict[str, Any]:
        rules = [rule for fragment in state.fragments for rule in fragment.rules]
        wanted: set[Atom] = {self.public.query}
        backward_rules: set[str] = set()
        unresolved: set[Atom] = set()
        changed = True
        while changed:
            changed = False
            for rule in rules:
                if rule.head not in wanted:
                    continue
                backward_rules.add(rule.signature)
                for premise in rule.body:
                    if premise not in state.closure:
                        unresolved.add(premise)
                        if premise not in wanted:
                            wanted.add(premise)
                            changed = True
        query_rules = [rule for rule in rules if rule.head == self.public.query]
        body_fraction = max(
            (
                sum(premise in state.closure for premise in rule.body) / len(rule.body)
                for rule in query_rules
            ),
            default=0.0,
        )
        return {
            "query_entailed": self.proved(state),
            "closure_size": len(state.closure),
            "committed_source_count": len(state.fragments),
            "rule_count": len(rules),
            "query_head_rule_count": len(query_rules),
            "best_query_body_satisfaction": body_fraction,
            "backward_relevant_rule_count": len(backward_rules),
            "unresolved_atoms": sorted(str(atom) for atom in unresolved),
        }

    def value(self, state: BranchState) -> float:
        if self.proved(state):
            return 1.0
        feedback = self.feedback(state)
        coverage = len(state.evaluated_window_ids) / max(1, len(self.window_actions))
        closure_mass = len(state.closure) / max(
            1,
            len(state.closure)
            + int(feedback["rule_count"])
            + int(feedback["committed_source_count"]),
        )
        value = (
            0.07 * coverage
            + 0.13 * closure_mass
            + 0.24 * min(1, int(feedback["query_head_rule_count"]))
            + 0.22 * float(feedback["best_query_body_satisfaction"])
            + 0.08 * min(2, int(feedback["backward_relevant_rule_count"]))
        )
        return min(0.94, value)

    def action_prior(self, state: BranchState, action: WindowAction) -> float:
        sources = [self.public.source_map[source_id] for source_id in action.source_ids]
        surface = "\n".join(f"{source.heading}\n{source.rendered_text}" for source in sources)
        surface_tokens = _tokens(surface)
        query_tokens = _tokens(self.public.query_text) | _tokens(str(self.public.query))
        overlap = len(query_tokens & surface_tokens) / max(1, len(query_tokens))
        feedback = self.feedback(state)
        frontier_bonus = 0.0
        surface_lower = surface.lower()
        for raw_atom in feedback["unresolved_atoms"] or [str(self.public.query)]:
            predicate = raw_atom.split("(", 1)[0].lower()
            if predicate and predicate in surface_lower:
                frontier_bonus += 1.0
        source_novelty = sum(
            source_id not in {fragment.source_id for fragment in state.fragments}
            for source_id in action.source_ids
        ) / max(1, len(action.source_ids))
        return 1.0 + 1.8 * overlap + 1.5 * frontier_bonus + 0.25 * source_novelty

    def normalised_priors(
        self, state: BranchState, actions: Sequence[WindowAction]
    ) -> dict[WindowAction, float]:
        raw = {action: max(1e-9, self.action_prior(state, action)) for action in actions}
        total = sum(raw.values())
        return {action: value / total for action, value in raw.items()}

    def _observe(self, action: WindowAction) -> tuple[WindowObservation, bool]:
        self.accounting.logical_window_evaluations += 1
        if self.accounting.logical_window_evaluations > self.logical_eval_cap:
            raise RuntimeError("hard logical window-evaluation cap exceeded")
        cached = self.observation_memo.get(action.action_id)
        if cached is not None:
            self.accounting.run_memo_hits += 1
            self.accounting.logical_replay_usage = add_stats(
                self.accounting.logical_replay_usage, cached.recorded_stats
            )
            return cached, True
        if self.accounting.unique_window_observations >= self.unique_call_cap:
            raise RuntimeError("hard unique-window/XHub-call cap reached")
        result = self.parser.parse(
            sources=[self.public.source_map[source_id] for source_id in action.source_ids],
            window_size=self.window_size,
        )
        observation = WindowObservation(
            action=action,
            fragments=tuple(
                sorted(result.fragments.values(), key=lambda fragment: fragment.source_id)
            ),
            valid_source_ids=tuple(sorted(result.valid_sources)),
            errors=tuple(sorted((str(key), str(value)) for key, value in result.errors.items())),
            response_model_id=result.response_model_id,
            parser_cache_hit=result.cache_hit,
            parser_cache_key=result.cache_key,
            new_stats=result.new_stats,
            recorded_stats=result.recorded_stats,
        )
        self.observation_memo[action.action_id] = observation
        self.accounting.unique_window_observations += 1
        self.accounting.parser_cache_hits += int(result.cache_hit)
        self.accounting.actual_usage = add_stats(
            self.accounting.actual_usage, result.new_stats
        )
        self.accounting.logical_replay_usage = add_stats(
            self.accounting.logical_replay_usage, result.recorded_stats
        )
        if self.accounting.actual_usage.calls > self.unique_call_cap:
            raise RuntimeError("hard paid XHub-call cap exceeded")
        return observation, False

    def step(
        self,
        state: BranchState,
        action: WindowAction,
        *,
        phase: str,
        branch_id: str,
    ) -> BranchState:
        if action not in self.actions(state):
            raise ValueError(f"illegal window action {action.action_id}")
        before_feedback = self.feedback(state)
        observation, memo_hit = self._observe(action)
        merged = _merge_state_fragments(
            self.public,
            state.fragments,
            observation.fragments,
        )
        after = _state_from_fragments(
            self.public,
            evaluated_window_ids=(*state.evaluated_window_ids, action.action_id),
            fragments=merged,
            remaining_commits=state.remaining_commits - 1,
        )
        after_feedback = self.feedback(after)
        self.accounting.events.append({
            "event_index": len(self.accounting.events),
            "phase": phase,
            "branch_id": branch_id,
            "action_id": action.action_id,
            "window_source_ids": list(action.source_ids),
            "remaining_commits_before": state.remaining_commits,
            "remaining_commits_after": after.remaining_commits,
            "run_memo_hit": memo_hit,
            "parser_cache_hit": observation.parser_cache_hit if not memo_hit else None,
            "parser_cache_key": observation.parser_cache_key,
            "response_model_id": observation.response_model_id,
            "valid_source_ids": list(observation.valid_source_ids),
            "parser_errors": dict(observation.errors),
            "validated_fragments": [
                fragment.as_dict() for fragment in observation.fragments
            ],
            "new_model_usage": (
                CallStats().as_dict() if memo_hit else observation.new_stats.as_dict()
            ),
            "logical_replay_usage": observation.recorded_stats.as_dict(),
            "feedback_before": before_feedback,
            "feedback_after": after_feedback,
            "closure_delta": sorted(str(atom) for atom in after.closure - state.closure),
            "semantic_state_key_sha256": sha256_text(canonical_json(self.state_key(after))),
        })
        return after


@dataclass
class EdgeStats:
    prior: float
    visits: int = 0
    value_sum: float = 0.0
    child_id: int | None = None

    @property
    def q(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


@dataclass
class PUCTNode:
    node_id: int
    state: BranchState
    visits: int = 0
    value_sum: float = 0.0
    edges: dict[WindowAction, EdgeStats] = field(default_factory=dict)


class GraphPUCTPlanner:
    """PUCT with an exact transposition table over semantic branch states."""

    def __init__(
        self,
        env: RealLLMGraphEnvironment,
        root_state: BranchState,
        *,
        seed: int,
        c_puct: float,
        rollout_depth: int,
        decision_index: int,
    ) -> None:
        self.env = env
        self.seed = seed
        self.c_puct = c_puct
        self.rollout_depth = rollout_depth
        self.decision_index = decision_index
        self.rng = random.Random(seed)
        self.nodes: dict[int, PUCTNode] = {}
        self.tt: dict[tuple[Any, ...], int] = {}
        self.tt_hits = 0
        self.transitions = 0
        self.simulations = 0
        self.root_id, _ = self._intern(root_state)

    def _intern(self, state: BranchState) -> tuple[int, bool]:
        key = self.env.state_key(state)
        if key in self.tt:
            self.tt_hits += 1
            return self.tt[key], True
        node_id = len(self.nodes)
        actions = self.env.actions(state)
        priors = self.env.normalised_priors(state, actions) if actions else {}
        self.nodes[node_id] = PUCTNode(
            node_id=node_id,
            state=state,
            edges={action: EdgeStats(prior) for action, prior in priors.items()},
        )
        self.tt[key] = node_id
        return node_id, False

    def _select(self, node: PUCTNode) -> WindowAction:
        unvisited = [action for action, edge in node.edges.items() if edge.visits == 0]
        if unvisited:
            return max(unvisited, key=lambda action: (node.edges[action].prior, action.action_id))
        root_visits = math.sqrt(max(1, node.visits))
        return max(
            node.edges,
            key=lambda action: (
                node.edges[action].q
                + self.c_puct
                * node.edges[action].prior
                * root_visits
                / (1 + node.edges[action].visits),
                node.edges[action].prior,
                action.action_id,
            ),
        )

    def simulate_once(self, transition_allowance: int) -> int:
        if transition_allowance <= 0 or self.env.remaining_logical() <= 0:
            return 0
        self.simulations += 1
        simulation_id = self.simulations
        node_id = self.root_id
        path: list[tuple[int, WindowAction]] = []
        consumed = 0
        depth = 0
        visited: set[int] = set()
        while (
            consumed < transition_allowance
            and depth < self.rollout_depth
            and self.env.remaining_logical() > 0
        ):
            node = self.nodes[node_id]
            if self.env.proved(node.state) or not node.edges or node_id in visited:
                break
            visited.add(node_id)
            action = self._select(node)
            child_state = self.env.step(
                node.state,
                action,
                phase="simulation",
                branch_id=f"d{self.decision_index}-s{simulation_id}",
            )
            consumed += 1
            depth += 1
            edge = node.edges[action]
            if edge.child_id is None:
                child_id, _ = self._intern(child_state)
                edge.child_id = child_id
            else:
                child_id = edge.child_id
                if self.env.state_key(child_state) != self.env.state_key(
                    self.nodes[child_id].state
                ):
                    raise AssertionError("memoized model outcome changed a PUCT child state")
            path.append((node_id, action))
            node_id = child_id
        leaf = self.nodes[node_id]
        value = self.env.value(leaf.state)
        leaf.visits += 1
        leaf.value_sum += value
        for parent_id, action in reversed(path):
            parent = self.nodes[parent_id]
            edge = parent.edges[action]
            edge.visits += 1
            edge.value_sum += value
            parent.visits += 1
            parent.value_sum += value
        self.transitions += consumed
        return consumed

    def run(self, *, transition_cap: int, simulation_cap: int) -> WindowAction | None:
        while self.transitions < transition_cap and self.simulations < simulation_cap:
            consumed = self.simulate_once(transition_cap - self.transitions)
            if consumed == 0:
                break
        root = self.nodes[self.root_id]
        if not root.edges:
            return None
        return max(
            root.edges,
            key=lambda action: (
                root.edges[action].visits,
                root.edges[action].q,
                root.edges[action].prior,
                action.action_id,
            ),
        )


def run_graphpuct_case(
    *,
    public: PublicCase,
    raw_public: Mapping[str, Any],
    parser: LEAWindowParser,
    window_size: int,
    real_window_cap: int,
    logical_eval_cap: int,
    unique_call_cap: int,
    simulation_transitions_per_move: int,
    simulations_per_move: int,
    rollout_depth: int,
    c_puct: float,
    seed: int,
) -> tuple[dict[str, Any], BranchState]:
    """Run search with no evaluator sidecar in scope."""
    env = RealLLMGraphEnvironment(
        public=public,
        raw_public=raw_public,
        parser=parser,
        window_size=window_size,
        real_window_cap=real_window_cap,
        logical_eval_cap=logical_eval_cap,
        unique_call_cap=unique_call_cap,
    )
    state = env.root()
    real_actions: list[str] = []
    planner_rows: list[dict[str, Any]] = []
    total_nodes = total_distinct_state_keys = 0
    total_tt_hits = total_simulations = total_simulation_transitions = 0
    decision = 0
    while env.actions(state) and env.remaining_logical() > 0:
        # Always reserve one logical evaluation for the chosen real commit.
        planning_cap = min(
            simulation_transitions_per_move,
            max(0, env.remaining_logical() - 1),
        )
        planner = GraphPUCTPlanner(
            env,
            state,
            seed=seed + 1009 * decision,
            c_puct=c_puct,
            rollout_depth=min(rollout_depth, state.remaining_commits),
            decision_index=decision,
        )
        action = planner.run(
            transition_cap=planning_cap,
            simulation_cap=simulations_per_move,
        )
        if action is None:
            break
        root_node = planner.nodes[planner.root_id]
        planner_rows.append({
            "decision_index": decision,
            "selected_action": action.action_id,
            "simulation_transitions": planner.transitions,
            "simulations": planner.simulations,
            "nodes": len(planner.nodes),
            "distinct_state_keys": len(planner.tt),
            "tt_hits": planner.tt_hits,
            "root_edges": [
                {
                    "action_id": candidate.action_id,
                    "prior": edge.prior,
                    "visits": edge.visits,
                    "q": edge.q,
                }
                for candidate, edge in sorted(
                    root_node.edges.items(), key=lambda item: item[0].action_id
                )
            ],
        })
        total_nodes += len(planner.nodes)
        total_distinct_state_keys += len(planner.tt)
        total_tt_hits += planner.tt_hits
        total_simulations += planner.simulations
        total_simulation_transitions += planner.transitions
        if env.remaining_logical() <= 0:
            break
        state = env.step(
            state,
            action,
            phase="real",
            branch_id=f"root-d{decision}",
        )
        real_actions.append(action.action_id)
        decision += 1
        if env.proved(state):
            break

    final_kb = _kb_from_fragments(state.fragments)
    final_lfp = least_fixed_point(final_kb)
    proof = final_lfp.proof(public.query)
    predicted = "Entailed" if proof is not None else "PR-Unknown"
    proof_valid = (
        verify_proof(final_kb, proof)
        and source_set_sufficient(final_kb, public.query, proof.source_ids)
        if proof is not None
        else True
    )
    trial = {
        "schema_version": SCHEMA_VERSION,
        "evidence_status": EVIDENCE_STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "case_id": public.case_id,
        "carrier_size": public.carrier_size,
        "condition": public.condition,
        "method": "GraphPUCT + XHub LLM + exact online LFP",
        "search_gold_access": False,
        "search_input": {
            "public_case_sha256": public.raw_public_sha256,
            "query_text": public.query_text,
            "query_atom": str(public.query),
            "source_count": len(public.sources),
            "window_count": len(env.window_actions),
            "window_size": window_size,
        },
        "caps": {
            "real_window_commit_cap": real_window_cap,
            "logical_window_evaluation_cap": logical_eval_cap,
            "unique_window_xhub_call_cap": unique_call_cap,
            "simulation_transitions_per_move": simulation_transitions_per_move,
            "simulations_per_move": simulations_per_move,
            "rollout_depth": rollout_depth,
        },
        "seed": seed,
        "c_puct": c_puct,
        "predicted_label": predicted,
        "proof_valid_on_model_kb": proof_valid,
        "proof": proof.as_dict() if proof else None,
        "real_action_ids": real_actions,
        "real_windows": [
            {
                "action_id": action_id,
                "source_ids": list(env.action_map[action_id].source_ids),
            }
            for action_id in real_actions
        ],
        "final_committed_source_ids": [fragment.source_id for fragment in state.fragments],
        "final_closure": [atom.as_dict() for atom in sorted(final_lfp.closure)],
        "final_lfp_iterations": final_lfp.iterations,
        "final_feedback": env.feedback(state),
        "metrics": {
            "real_window_commits": len(real_actions),
            "logical_window_evaluations": env.accounting.logical_window_evaluations,
            "unique_window_observations": env.accounting.unique_window_observations,
            "run_memo_hits": env.accounting.run_memo_hits,
            "parser_cache_hits": env.accounting.parser_cache_hits,
            "actual_xhub_usage": env.accounting.actual_usage.as_dict(),
            "logical_uncached_replay_usage": env.accounting.logical_replay_usage.as_dict(),
            "puct_nodes": total_nodes,
            "puct_distinct_state_keys": total_distinct_state_keys,
            "puct_tt_hits": total_tt_hits,
            "puct_simulations": total_simulations,
            "puct_simulation_transitions": total_simulation_transitions,
        },
        "planner_decisions": planner_rows,
        "ledger": env.accounting.events,
        "observed_model_ids": sorted({
            observation.response_model_id
            for observation in env.observation_memo.values()
            if observation.response_model_id
        }),
    }
    return trial, state


def _gold_kb_for_sources(
    public: PublicCase,
    sidecar: EvaluatorSidecar,
    source_ids: Iterable[str],
) -> CommittedKB:
    fragments = [
        gold_fragment(public.source_map[source_id], sidecar)
        for source_id in sorted(set(source_ids))
    ]
    return _kb_from_fragments(fragments)


def evaluate_after_search(
    trial: Mapping[str, Any],
    state: BranchState,
    public: PublicCase,
    sidecar: EvaluatorSidecar,
) -> dict[str, Any]:
    """Attach evaluator-only fields after search is irreversibly complete."""
    if public.case_id != sidecar.case_id:
        raise ValueError("public/evaluator case mismatch")
    proof_raw = trial.get("proof")
    predicted = str(trial["predicted_label"])
    proof_sources = tuple(proof_raw.get("source_ids", [])) if isinstance(proof_raw, Mapping) else ()
    gold_support_valid = (
        least_fixed_point(_gold_kb_for_sources(public, sidecar, proof_sources)).entails(
            public.query
        )
        if proof_sources
        else predicted == "PR-Unknown"
    )
    oracle_cover = set(sidecar.raw.get("oracle", {}).get("minimum_source_cover", []) or [])
    source_exactness: list[dict[str, Any]] = []
    for fragment in state.fragments:
        gold = gold_fragment(public.source_map[fragment.source_id], sidecar)
        source_exactness.append({
            "source_id": fragment.source_id,
            "semantic_exact": fragment.semantic_signature == gold.semantic_signature,
            "model_fact_count": len(fragment.facts),
            "model_rule_count": len(fragment.rules),
            "gold_fact_count": len(gold.facts),
            "gold_rule_count": len(gold.rules),
        })
    label_exact = predicted == sidecar.expected_label
    strict = (
        label_exact
        and bool(trial["proof_valid_on_model_kb"])
        and gold_support_valid
        and (predicted != "Entailed" or bool(proof_sources))
    )
    return {
        **trial,
        "evaluation_loaded_after_search": True,
        "expected_label": sidecar.expected_label,
        "label_exact": label_exact,
        "strict_answer_and_proof": strict,
        "gold_support_valid": gold_support_valid,
        "unknown_false_entailment": (
            sidecar.expected_label == "PR-Unknown" and predicted == "Entailed"
        ),
        "exact_minimum_source_cover": (
            predicted == "Entailed" and set(proof_sources) == oracle_cover
        ),
        "gold_minimum_source_cover": sorted(oracle_cover),
        "source_semantic_exactness": source_exactness,
    }


def _aggregate(trials: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    actual = CallStats()
    logical = CallStats()
    for trial in trials:
        metrics = trial["metrics"]
        actual = add_stats(actual, stats_from_dict(metrics["actual_xhub_usage"]))
        logical = add_stats(logical, stats_from_dict(metrics["logical_uncached_replay_usage"]))
    gates = {
        "two_fixed_cases_present": len(trials) == 2,
        "productive_strict_pass": any(
            row["condition"] == "Productive" and row["strict_answer_and_proof"]
            for row in trials
        ),
        "clean_unknown_safe": any(
            row["condition"] == "Clean"
            and row["strict_answer_and_proof"]
            and not row["unknown_false_entailment"]
            for row in trials
        ),
        "real_xhub_was_called": actual.calls > 0,
        "all_caps_respected": all(
            row["metrics"]["logical_window_evaluations"]
            <= row["caps"]["logical_window_evaluation_cap"]
            and row["metrics"]["actual_xhub_usage"]["calls"]
            <= row["caps"]["unique_window_xhub_call_cap"]
            and row["metrics"]["real_window_commits"]
            <= row["caps"]["real_window_commit_cap"]
            for row in trials
        ),
        "search_gold_access_false": all(not row["search_gold_access"] for row in trials),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(gates.values()) else "FAIL",
        "status_interpretation": (
            "PASS means the two-case end-to-end mechanism and safety gates passed; "
            "it does not establish a performance advantage."
        ),
        "evidence_status": EVIDENCE_STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "gates": gates,
        "case_count": len(trials),
        "cases": [
            {
                "case_id": row["case_id"],
                "condition": row["condition"],
                "predicted_label": row["predicted_label"],
                "expected_label": row["expected_label"],
                "strict_answer_and_proof": row["strict_answer_and_proof"],
                "real_window_commits": row["metrics"]["real_window_commits"],
                "logical_window_evaluations": row["metrics"]["logical_window_evaluations"],
                "actual_xhub_calls": row["metrics"]["actual_xhub_usage"]["calls"],
                "actual_xhub_tokens": row["metrics"]["actual_xhub_usage"]["total_tokens"],
                "puct_tt_hits": row["metrics"]["puct_tt_hits"],
            }
            for row in trials
        ],
        "actual_xhub_usage": actual.as_dict(),
        "logical_uncached_replay_usage": logical.as_dict(),
        "totals": {
            "real_window_commits": sum(row["metrics"]["real_window_commits"] for row in trials),
            "logical_window_evaluations": sum(
                row["metrics"]["logical_window_evaluations"] for row in trials
            ),
            "unique_window_observations": sum(
                row["metrics"]["unique_window_observations"] for row in trials
            ),
            "run_memo_hits": sum(row["metrics"]["run_memo_hits"] for row in trials),
            "puct_tt_hits": sum(row["metrics"]["puct_tt_hits"] for row in trials),
        },
    }


def _select_public_cases(
    public_path: Path,
    *,
    sizes: set[int],
    conditions: set[str],
    per_condition: int,
) -> tuple[list[tuple[PublicCase, Mapping[str, Any]]], dict[str, Any]]:
    buckets: dict[tuple[int, str], list[tuple[PublicCase, Mapping[str, Any]]]] = defaultdict(list)
    for raw in read_jsonl(public_path):
        public = _public_case(raw)
        if public.carrier_size in sizes and public.condition.lower() in conditions:
            buckets[(public.carrier_size, public.condition.lower())].append((public, raw))
    selected: list[tuple[PublicCase, Mapping[str, Any]]] = []
    for key in sorted(buckets):
        selected.extend(sorted(buckets[key], key=lambda pair: pair[0].case_id)[:per_condition])
    return selected, {
        "requested_sizes": sorted(sizes),
        "requested_conditions": sorted(conditions),
        "per_size_condition": per_condition,
        "selected_case_ids": [pair[0].case_id for pair in selected],
        "selected_windows": {
            pair[0].case_id: len(_window_actions(pair[1], 4)) for pair in selected
        },
    }


def _load_sidecars(path: Path) -> dict[str, EvaluatorSidecar]:
    return {str(raw["case_id"]): _sidecar(raw) for raw in read_jsonl(path)}


def _secret_scan(paths: Sequence[Path], secret: str) -> None:
    if not secret:
        raise RuntimeError("empty API key during output secret scan")
    needle = secret.encode("utf-8")
    for path in paths:
        if path.exists() and needle in path.read_bytes():
            raise RuntimeError(f"credential material leaked into {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", type=Path, default=DEFAULT_PUBLIC)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--sizes", default="9")
    parser.add_argument("--conditions", default="Productive,Clean")
    parser.add_argument("--per-size-condition", type=int, default=1)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--real-window-cap", type=int, default=3)
    parser.add_argument("--logical-eval-cap", type=int, default=24)
    parser.add_argument("--unique-call-cap", type=int, default=8)
    parser.add_argument("--simulation-transitions-per-move", type=int, default=8)
    parser.add_argument("--simulations-per-move", type=int, default=4)
    parser.add_argument("--rollout-depth", type=int, default=3)
    parser.add_argument("--c-puct", type=float, default=1.35)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--model", default=DEFAULT_XHUB_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_XHUB_BASE_URL)
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--num-ctx", type=int, default=32_768)
    parser.add_argument("--max-tokens", type=int, default=4_096)
    parser.add_argument("--refresh-cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sizes = {int(item.strip()) for item in args.sizes.split(",") if item.strip()}
    conditions = {item.strip().lower() for item in args.conditions.split(",") if item.strip()}
    selected, coverage = _select_public_cases(
        args.public,
        sizes=sizes,
        conditions=conditions,
        per_condition=args.per_size_condition,
    )
    if not selected:
        raise RuntimeError("no public cases survived the Phase-5 filters")
    max_unique = sum(
        min(args.unique_call_cap, len(_window_actions(raw, args.window_size)))
        for _, raw in selected
    )
    if args.dry_run:
        print(json.dumps({
            "status": "DRY_RUN_NO_MODEL_CALLS",
            "coverage": coverage,
            "caps_per_case": {
                "real_window_cap": args.real_window_cap,
                "logical_eval_cap": args.logical_eval_cap,
                "unique_call_cap": args.unique_call_cap,
            },
            "maximum_new_xhub_calls": max_unique,
            "maximum_logical_window_evaluations": args.logical_eval_cap * len(selected),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    load_dotenv(ROOT.parents[3] / ".env")
    client = OpenAICompatibleClient(
        model=args.model,
        base_url=args.base_url,
        api_key_env=args.api_key_env,
        timeout_seconds=args.timeout_seconds,
        num_ctx=args.num_ctx,
        max_tokens=args.max_tokens,
    )
    if client.provider != "xhub":
        raise AssertionError("Phase 5 permits XHub only")
    args.results_dir.mkdir(parents=True, exist_ok=True)
    cache_path = args.results_dir / "xhub_window_cache.jsonl"
    parser = LEAWindowParser(client, cache_path, refresh=args.refresh_cache)

    # Crucial separation: sidecars are not loaded until this entire loop ends.
    search_outputs: list[tuple[dict[str, Any], BranchState, PublicCase]] = []
    for public, raw_public in selected:
        trial, state = run_graphpuct_case(
            public=public,
            raw_public=raw_public,
            parser=parser,
            window_size=args.window_size,
            real_window_cap=args.real_window_cap,
            logical_eval_cap=args.logical_eval_cap,
            unique_call_cap=args.unique_call_cap,
            simulation_transitions_per_move=args.simulation_transitions_per_move,
            simulations_per_move=args.simulations_per_move,
            rollout_depth=args.rollout_depth,
            c_puct=args.c_puct,
            seed=args.seed,
        )
        search_outputs.append((trial, state, public))

    sidecars = _load_sidecars(args.gold)
    trials = [
        evaluate_after_search(trial, state, public, sidecars[public.case_id])
        for trial, state, public in search_outputs
    ]
    summary = _aggregate(trials)
    summary["coverage"] = coverage
    summary["model"] = {
        "provider": client.provider,
        "base_url_host": client.base_url_host,
        "requested_model": client.model,
        "observed_model_ids": sorted({
            model_id for trial in trials for model_id in trial["observed_model_ids"]
        }),
        "model_revision": client.model_revision,
        "temperature": client.temperature,
        "max_tokens": client.max_tokens,
        "diagnostic_assumed_context_limit": client.num_ctx,
        "request_protocol": JSON_REQUEST_PROTOCOL,
        "api_key_env": client.api_key_env,
    }
    summary["protocol"] = {
        "window_policy": "center + directed-neighbor + SCC-order fill; unordered duplicates removed",
        "parser": "query-independent XHub window parser + fail-closed source-grounded validator",
        "branch_commit": "validated fragments only; overlapping source observations unioned by Horn semantics",
        "feedback": "exact LFP closure, query-rule body satisfaction, and unresolved predicates",
        "graph_merge": "exact semantic transposition-table key; action order is not part of the key",
        "accounting": "logical evaluations, run memo hits, parser cache hits, and actual paid XHub calls separated",
        "gold_boundary": "gold sidecar loaded only after all search cases completed",
    }

    trials_path = args.results_dir / "trials.jsonl"
    summary_path = args.results_dir / "summary.json"
    write_jsonl(trials_path, trials)
    write_json(summary_path, summary)
    output_paths = [trials_path, summary_path, cache_path]
    api_key = os.environ.get(args.api_key_env, "")
    _secret_scan(output_paths, api_key)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_utc": summary["run_utc"],
        "runner": str(SCRIPT_PATH),
        "python": sys.version,
        "platform": platform.platform(),
        "claim_boundary": CLAIM_BOUNDARY,
        "search_gold_access": False,
        "gold_loaded_after_all_searches": True,
        "local_model_used": False,
        "provider": client.provider,
        "maximum_new_xhub_calls_predeclared": max_unique,
        "actual_new_xhub_calls": summary["actual_xhub_usage"]["calls"],
        "inputs": {
            str(path): {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in (
                args.public,
                args.gold,
                SCRIPT_PATH,
                ROOT / "lfp_core.py",
                ROOT / "local_parser.py",
                ROOT / "run_phase4_baselines.py",
                LEA_SYSTEM,
                LEA_SCHEMA,
            )
        },
        "outputs": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in output_paths
        },
        "security_gates": {
            "api_key_value_absent_from_outputs": True,
            "xhub_only": client.provider == "xhub",
            "raw_model_cache_hashed": cache_path.exists(),
        },
    }
    manifest_path = args.results_dir / "manifest.json"
    write_json(manifest_path, manifest)
    _secret_scan([manifest_path], api_key)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
