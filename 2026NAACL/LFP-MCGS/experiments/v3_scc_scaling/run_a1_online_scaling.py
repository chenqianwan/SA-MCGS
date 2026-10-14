#!/usr/bin/env python3
"""A1 online/receding-horizon TreeMCTS vs strict state-sharing MCGS.

This is an oracle-outcome *diagnostic*.  Every planning decision starts from
the current committed state, spends a fixed simulator-transition allowance,
executes exactly one charged real root action, and then replans.  A real or
simulated source payload enters a branch only when that branch executes an
``acquire`` action.  The reward never reads the unrevealed full program,
generator proof, source role, or query-ancestor cone.

TreeMCTS retains the selected child's reachable subtree after each real action.
MCGS uses the same code and additionally merges nodes with the strict key

    (current source, acquired mask, exact closure, obligations, budget left).

The bidirectional/chorded overlay is a deliberately synthetic opportunity
diagnostic.  Canonical and overlay results must never be pooled as if both were
native benchmark topology.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import run_a0_scc_scaling as a0


SCRIPT_PATH = Path(__file__).resolve()
EXPERIMENT_ROOT = SCRIPT_PATH.parent
DEFAULT_INPUT = EXPERIMENT_ROOT / "data" / "benchmark.jsonl"
DEFAULT_RESULTS_DIR = EXPERIMENT_ROOT / "results" / "a1_online_smoke"
NAVIGATION_VARIANTS = ("canonical", "bidirectional_chorded_core_overlay")
METHODS = (("tree_mcts", False), ("mcgs", True))
EVIDENCE_STATUS = "oracle_structure_online_diagnostic"
CLAIM_BOUNDARY = (
    "A1 is a synthetic oracle-outcome, receding-horizon mechanism diagnostic. "
    "It is not an LLM, natural-language, token-cost, natural-corpus, or "
    "confirmatory superiority result; the overlay is not native data topology."
)


def atom_dict(atom: a0.Atom) -> dict[str, Any]:
    return {"predicate": atom.predicate, "arguments": list(atom.arguments)}


def source_payload(source: a0.SourceNode) -> list[dict[str, Any]]:
    payloads = [
        {"kind": "fact", "head": atom_dict(fact), "body": []}
        for fact in source.facts
    ]
    payloads.extend(
        {
            "kind": "rule",
            "head": atom_dict(rule.head),
            "body": [atom_dict(premise) for premise in rule.body],
        }
        for rule in source.rules
    )
    return payloads


def state_dict(state: a0.NavigationState) -> dict[str, Any]:
    return {
        "current_node": state.current_node,
        "acquired_mask": state.acquired_mask,
        "acquired_count": state.acquired_mask.bit_count(),
        "closure": [atom.text for atom in state.closure],
        "obligations": [atom.text for atom in state.obligations],
        "remaining_budget": state.remaining_budget,
    }


class OnlineRevealEnvironment:
    """Branch-local exact Horn environment with no unrevealed-gold reward access."""

    def __init__(self, case: a0.BenchmarkCase, navigation_variant: str):
        if navigation_variant not in NAVIGATION_VARIANTS:
            raise ValueError(f"unknown navigation variant {navigation_variant!r}")
        self.case = case
        self.navigation_variant = navigation_variant
        self.source_map = case.source_map
        self.source_index = case.source_index
        self.adjacency = self._build_adjacency(navigation_variant)
        self._summary_cache: dict[int, tuple[tuple[a0.Atom, ...], tuple[a0.Atom, ...]]] = {}

    def _build_adjacency(self, navigation_variant: str) -> dict[str, tuple[str, ...]]:
        if navigation_variant == "canonical":
            return {
                source_id: tuple(neighbors)
                for source_id, neighbors in self.case.adjacency.items()
            }

        # Identical source-ID overlay rule in every semantic condition.  Native
        # canonical edges are retained, so this is explicitly a stress overlay,
        # not a replacement benchmark graph.
        adjacency = {
            source_id: set(neighbors)
            for source_id, neighbors in self.case.adjacency.items()
        }
        core_rules = sorted(
            source.source_id
            for source in self.case.sources
            if source.source_id.startswith("src_core_rule_")
        )
        if not core_rules:
            raise ValueError(f"{self.case.case_id}: overlay requires core rule nodes")

        def connect(left: str, right: str) -> None:
            if left != right:
                adjacency[left].add(right)
                adjacency[right].add(left)

        connect(self.case.root_source_id, core_rules[0])
        for index, source_id in enumerate(core_rules):
            connect(source_id, core_rules[(index + 1) % len(core_rules)])
        if len(core_rules) >= 4:
            for index, source_id in enumerate(core_rules):
                connect(source_id, core_rules[(index + 2) % len(core_rules)])
        return {
            source_id: tuple(sorted(neighbors))
            for source_id, neighbors in adjacency.items()
        }

    @property
    def signature(self) -> str:
        return hashlib.sha256(
            a0.canonical_json({
                "case_id": self.case.case_id,
                "variant": self.navigation_variant,
                "query": self.case.query.text,
                "source_ids": self.case.source_ids,
                "adjacency": self.adjacency,
                "budget": self.case.action_budget,
            }).encode()
        ).hexdigest()

    def _program_for_mask(self, mask: int) -> tuple[list[a0.Atom], list[a0.HornRule]]:
        facts: list[a0.Atom] = []
        rules: list[a0.HornRule] = []
        for index, source in enumerate(self.case.sources):
            if mask & (1 << index):
                facts.extend(source.facts)
                rules.extend(source.rules)
        return facts, rules

    def _summarize_mask(self, mask: int) -> tuple[tuple[a0.Atom, ...], tuple[a0.Atom, ...]]:
        cached = self._summary_cache.get(mask)
        if cached is not None:
            return cached
        facts, rules = self._program_for_mask(mask)
        closure = a0.positive_horn_closure(facts, rules)
        obligations = a0.recursive_obligations(self.case.query, closure, rules)
        summary = tuple(sorted(closure)), obligations
        self._summary_cache[mask] = summary
        return summary

    def make_state(
        self, current_node: str, acquired_mask: int, remaining_budget: int
    ) -> a0.NavigationState:
        closure, obligations = self._summarize_mask(acquired_mask)
        return a0.NavigationState(
            current_node,
            acquired_mask,
            closure,
            obligations,
            remaining_budget,
        )

    def root(self) -> a0.NavigationState:
        return self.make_state(self.case.root_source_id, 0, self.case.action_budget)

    def is_proof(self, state: a0.NavigationState) -> bool:
        return self.case.query in state.closure

    def actions(self, state: a0.NavigationState) -> tuple[a0.Action, ...]:
        if state.remaining_budget <= 0 or self.is_proof(state):
            return tuple()
        actions: list[a0.Action] = []
        index = self.source_index[state.current_node]
        if not state.acquired_mask & (1 << index):
            actions.append(a0.Action("acquire", state.current_node))
        actions.extend(
            a0.Action("move", neighbor)
            for neighbor in self.adjacency[state.current_node]
        )
        return tuple(sorted(actions))

    def action_prior(self, state: a0.NavigationState, action: a0.Action) -> float:
        # No source role, text, formal payload, proof source, or full closure is read.
        if action.kind == "acquire":
            return 1.0
        target_index = self.source_index[action.target]
        return 0.62 if not state.acquired_mask & (1 << target_index) else 0.20

    def transition(
        self, state: a0.NavigationState, action: a0.Action
    ) -> a0.NavigationState:
        if action not in self.actions(state):
            raise ValueError(f"illegal action {action.text} from {state.key}")
        if action.kind == "acquire":
            index = self.source_index[state.current_node]
            return self.make_state(
                state.current_node,
                state.acquired_mask | (1 << index),
                state.remaining_budget - 1,
            )
        if action.kind == "move":
            return self.make_state(
                action.target,
                state.acquired_mask,
                state.remaining_budget - 1,
            )
        raise ValueError(action.kind)

    def reward(self, state: a0.NavigationState) -> float:
        """Visible-state-only shaping shared exactly by TreeMCTS and MCGS."""
        if self.is_proof(state):
            efficiency = state.remaining_budget / max(1, self.case.action_budget)
            return 1.0 + 0.05 * efficiency
        acquired = max(1, state.acquired_mask.bit_count())
        closure_productivity = min(1.0, len(state.closure) / acquired)
        obligation_score = 1.0 / (1.0 + len(state.obligations))
        coverage = state.acquired_mask.bit_count() / max(1, len(self.case.sources))
        return 0.52 * closure_productivity + 0.32 * obligation_score + 0.11 * coverage


@dataclass
class EdgeStats:
    child_id: str
    visits: int = 0
    value_sum: float = 0.0

    @property
    def q(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


@dataclass
class SearchNode:
    node_id: str
    state: a0.NavigationState
    created_decision: int
    visits: int = 0
    value_sum: float = 0.0
    edges: dict[a0.Action, EdgeStats] = field(default_factory=dict)


class PersistentOnlineSearch:
    """Persistent selected-subtree search; ``merge_states`` is the sole switch."""

    def __init__(
        self,
        environment: OnlineRevealEnvironment,
        seed: int,
        exploration_constant: float,
        merge_states: bool,
    ):
        self.env = environment
        self.seed = seed
        self.exploration_constant = exploration_constant
        self.merge_states = merge_states
        self.nodes: dict[str, SearchNode] = {}
        self.state_index: dict[tuple[Any, ...], str] = {}
        self.next_node_id = 0
        self.current_decision = -1

        self.simulation_transitions = 0
        self.simulations = 0
        self.nodes_created_total = 0
        self.nodes_pruned_total = 0
        self.peak_live_nodes = 0
        self.expansions = 0
        self.tt_lookups = 0
        self.tt_hits = 0
        self.cross_root_tt_hits = 0
        self.backprop_updates = 0
        self.simulated_proof_terminals = 0
        self.unique_sim_transition_keys: set[tuple[Any, ...]] = set()
        self.rebase_trace: list[dict[str, Any]] = []

        root = self._create_or_merge(self.env.root(), created_decision=-1)
        self.root_id = root.node_id

    @property
    def root(self) -> SearchNode:
        return self.nodes[self.root_id]

    def _create_or_merge(
        self,
        state: a0.NavigationState,
        *,
        created_decision: int,
    ) -> SearchNode:
        if self.merge_states:
            self.tt_lookups += 1
            existing_id = self.state_index.get(state.key)
            if existing_id is not None:
                existing = self.nodes[existing_id]
                if existing.state != state:
                    raise AssertionError("strict state key collision")
                if self.env.actions(existing.state) != self.env.actions(state):
                    raise AssertionError("merged states are not decision equivalent")
                self.tt_hits += 1
                if existing.created_decision < self.current_decision:
                    self.cross_root_tt_hits += 1
                return existing
        node_id = f"n{self.next_node_id}"
        self.next_node_id += 1
        node = SearchNode(node_id, state, created_decision)
        self.nodes[node_id] = node
        self.nodes_created_total += 1
        self.peak_live_nodes = max(self.peak_live_nodes, len(self.nodes))
        if self.merge_states:
            self.state_index[state.key] = node_id
        return node

    def _jitter(
        self,
        decision: int,
        simulation: int,
        depth: int,
        state: a0.NavigationState,
        action: a0.Action,
        purpose: str,
    ) -> float:
        return a0.stable_unit(
            "a1-counter-rng-v1",
            self.seed,
            purpose,
            decision,
            simulation,
            depth,
            state.key,
            action.text,
        )

    def _choose_unexpanded(
        self,
        actions: Sequence[a0.Action],
        state: a0.NavigationState,
        decision: int,
        simulation: int,
        depth: int,
    ) -> a0.Action:
        return max(
            actions,
            key=lambda action: (
                self.env.action_prior(state, action),
                self._jitter(
                    decision, simulation, depth, state, action, "unexpanded"
                ),
                action.text,
            ),
        )

    def _choose_ucb(
        self,
        node: SearchNode,
        decision: int,
        simulation: int,
        depth: int,
    ) -> a0.Action:
        log_parent = math.log(max(2, node.visits + 1))
        return max(
            node.edges,
            key=lambda action: (
                node.edges[action].q
                + self.exploration_constant
                * self.env.action_prior(node.state, action)
                * math.sqrt(log_parent / (1 + node.edges[action].visits)),
                self._jitter(decision, simulation, depth, node.state, action, "ucb"),
                action.text,
            ),
        )

    def _choose_rollout(
        self,
        state: a0.NavigationState,
        decision: int,
        simulation: int,
        depth: int,
    ) -> a0.Action:
        return max(
            self.env.actions(state),
            key=lambda action: (
                self.env.action_prior(state, action)
                + 0.35
                * self._jitter(
                    decision, simulation, depth, state, action, "rollout"
                ),
                action.text,
            ),
        )

    def _sim_step(
        self, state: a0.NavigationState, action: a0.Action
    ) -> a0.NavigationState:
        successor = self.env.transition(state, action)
        self.simulation_transitions += 1
        self.unique_sim_transition_keys.add((state.key, action.text))
        return successor

    def _simulate_once(
        self,
        decision: int,
        local_simulation: int,
        transition_limit: int,
    ) -> int:
        node = self.root
        path_nodes = [node]
        path_edges: list[tuple[SearchNode, a0.Action]] = []
        depth = 0
        transitions_before = self.simulation_transitions
        expanded = False

        while self.simulation_transitions < transition_limit:
            actions = self.env.actions(node.state)
            if not actions:
                break
            unexpanded = [action for action in actions if action not in node.edges]
            if unexpanded:
                action = self._choose_unexpanded(
                    unexpanded,
                    node.state,
                    decision,
                    local_simulation,
                    depth,
                )
                successor = self._sim_step(node.state, action)
                child = self._create_or_merge(
                    successor,
                    created_decision=decision,
                )
                node.edges[action] = EdgeStats(child.node_id)
                self.expansions += 1
                path_edges.append((node, action))
                node = child
                path_nodes.append(node)
                depth += 1
                expanded = True
                break
            action = self._choose_ucb(
                node, decision, local_simulation, depth
            )
            successor = self._sim_step(node.state, action)
            child = self.nodes[node.edges[action].child_id]
            if successor != child.state:
                raise AssertionError("stored edge disagrees with exact transition")
            path_edges.append((node, action))
            node = child
            path_nodes.append(node)
            depth += 1

        final_state = node.state
        if expanded:
            while self.simulation_transitions < transition_limit:
                actions = self.env.actions(final_state)
                if not actions:
                    break
                action = self._choose_rollout(
                    final_state,
                    decision,
                    local_simulation,
                    depth,
                )
                final_state = self._sim_step(final_state, action)
                depth += 1

        reward = self.env.reward(final_state)
        for visited in path_nodes:
            visited.visits += 1
            visited.value_sum += reward
            self.backprop_updates += 1
        for parent, action in path_edges:
            parent.edges[action].visits += 1
            parent.edges[action].value_sum += reward
        if self.env.is_proof(final_state):
            self.simulated_proof_terminals += 1
        self.simulations += 1
        return self.simulation_transitions - transitions_before

    def plan_decision(
        self,
        decision: int,
        simulations_per_decision: int,
        transition_cap_per_decision: int,
    ) -> dict[str, Any]:
        self.current_decision = decision
        transition_start = self.simulation_transitions
        simulation_start = self.simulations
        node_start = self.nodes_created_total
        tt_lookup_start = self.tt_lookups
        tt_hit_start = self.tt_hits
        cross_root_hit_start = self.cross_root_tt_hits
        absolute_transition_limit = transition_start + transition_cap_per_decision

        stagnant = 0
        for local_simulation in range(simulations_per_decision):
            if self.simulation_transitions >= absolute_transition_limit:
                break
            if not self.env.actions(self.root.state):
                break
            used = self._simulate_once(
                decision,
                local_simulation,
                absolute_transition_limit,
            )
            if used == 0:
                stagnant += 1
                if stagnant >= 2:
                    break
            else:
                stagnant = 0

        choices = []
        for action in self.env.actions(self.root.state):
            edge = self.root.edges.get(action)
            choices.append({
                "action": action.text,
                "expanded": edge is not None,
                "visits": edge.visits if edge else 0,
                "q": edge.q if edge else 0.0,
                "prior": self.env.action_prior(self.root.state, action),
                "child_id": edge.child_id if edge else None,
            })
        return {
            "decision": decision,
            "simulations": self.simulations - simulation_start,
            "simulation_transitions": self.simulation_transitions - transition_start,
            "transition_cap": transition_cap_per_decision,
            "nodes_created": self.nodes_created_total - node_start,
            "live_nodes_before_real_action": len(self.nodes),
            "tt_lookups": self.tt_lookups - tt_lookup_start,
            "tt_hits": self.tt_hits - tt_hit_start,
            "cross_root_tt_hits": self.cross_root_tt_hits - cross_root_hit_start,
            "root_choices": choices,
        }

    def choose_real_root_action(self, decision: int) -> a0.Action:
        actions = self.env.actions(self.root.state)
        if not actions:
            raise RuntimeError("cannot choose from a terminal real root")
        return max(
            actions,
            key=lambda action: (
                self.root.edges[action].visits if action in self.root.edges else 0,
                self.root.edges[action].q if action in self.root.edges else 0.0,
                self.env.action_prior(self.root.state, action),
                self._jitter(decision, -1, 0, self.root.state, action, "real-root"),
                action.text,
            ),
        )

    def _reachable_from(self, start_id: str) -> set[str]:
        reachable = {start_id}
        pending = [start_id]
        while pending:
            node = self.nodes[pending.pop()]
            for edge in node.edges.values():
                if edge.child_id not in reachable:
                    reachable.add(edge.child_id)
                    pending.append(edge.child_id)
        return reachable

    def commit_real_action(
        self,
        decision: int,
        action: a0.Action,
        successor: a0.NavigationState,
    ) -> dict[str, Any]:
        old_root = self.root
        edge = old_root.edges.get(action)
        selected_child_preexisting = edge is not None
        if edge is not None:
            child = self.nodes[edge.child_id]
            if child.state != successor:
                raise AssertionError("selected simulated child differs from real outcome")
        else:
            child = self._create_or_merge(
                successor,
                created_decision=decision,
            )
            old_root.edges[action] = EdgeStats(child.node_id)

        reachable = self._reachable_from(child.node_id)
        live_before = len(self.nodes)
        incoming: Counter[str] = Counter()
        for node_id in reachable:
            for edge_stats in self.nodes[node_id].edges.values():
                if edge_stats.child_id in reachable:
                    incoming[edge_stats.child_id] += 1
        retained_transposed_nodes = sum(count > 1 for count in incoming.values())
        for node_id in list(self.nodes):
            if node_id not in reachable:
                del self.nodes[node_id]
        pruned = live_before - len(self.nodes)
        self.nodes_pruned_total += pruned
        self.root_id = child.node_id
        if self.merge_states:
            self.state_index = {
                node.state.key: node_id for node_id, node in self.nodes.items()
            }
            if len(self.state_index) != len(self.nodes):
                raise AssertionError("strict MCGS graph retained duplicate exact states")

        record = {
            "decision": decision,
            "selected_child_preexisting": selected_child_preexisting,
            "live_nodes_before_rebase": live_before,
            "retained_nodes": len(self.nodes),
            "pruned_nodes": pruned,
            "retained_transposed_nodes": retained_transposed_nodes,
        }
        self.rebase_trace.append(record)
        return record


def run_trial(
    case: a0.BenchmarkCase,
    navigation_variant: str,
    method: str,
    merge_states: bool,
    seed: int,
    simulations_per_decision: int,
    transition_cap_per_decision: int,
    exploration_constant: float,
) -> dict[str, Any]:
    env = OnlineRevealEnvironment(case, navigation_variant)
    search = PersistentOnlineSearch(env, seed, exploration_constant, merge_states)
    state = env.root()
    real_ledger = []
    closure_trace = [{
        "decision": -1,
        "after_action": None,
        "closure": [atom.text for atom in state.closure],
        "new_atoms": [],
    }]
    planning_trace = []
    revealed_source_ids: list[str] = []

    decision = 0
    while state.remaining_budget > 0 and not env.is_proof(state):
        if state != search.root.state:
            raise AssertionError("persistent search root diverged from committed state")
        if not env.actions(state):
            break
        planning = search.plan_decision(
            decision,
            simulations_per_decision,
            transition_cap_per_decision,
        )
        action = search.choose_real_root_action(decision)
        before = state
        successor = env.transition(before, action)
        if successor.remaining_budget != before.remaining_budget - 1:
            raise AssertionError("a real root action must cost exactly one budget unit")
        if action.kind == "move":
            if successor.acquired_mask != before.acquired_mask:
                raise AssertionError("move action revealed a formal payload")
            if successor.closure != before.closure:
                raise AssertionError("move action changed committed closure")
            revealed_payload = None
        else:
            if action.target != before.current_node:
                raise AssertionError("acquire must reveal the current physical source")
            revealed_source_ids.append(action.target)
            revealed_payload = source_payload(env.source_map[action.target])

        old_closure = set(before.closure)
        new_atoms = sorted(atom.text for atom in set(successor.closure) - old_closure)
        rebase = search.commit_real_action(decision, action, successor)
        planning["selected_action"] = action.text
        planning["rebase"] = rebase
        planning_trace.append(planning)
        ledger_row = {
            "decision": decision,
            "charged_cost": 1,
            "action": action.text,
            "kind": action.kind,
            "target": action.target,
            "state_before": state_dict(before),
            "state_after": state_dict(successor),
            "revealed_source_id": action.target if action.kind == "acquire" else None,
            "revealed_formal_payload": revealed_payload,
            "new_closure_atoms": new_atoms,
            "proof_after_action": env.is_proof(successor),
        }
        real_ledger.append(ledger_row)
        closure_trace.append({
            "decision": decision,
            "after_action": action.text,
            "closure": [atom.text for atom in successor.closure],
            "new_atoms": new_atoms,
        })
        state = successor
        decision += 1

    distinct_live_state_keys = len({node.state.key for node in search.nodes.values()})
    if merge_states and distinct_live_state_keys != len(search.nodes):
        raise AssertionError("MCGS final graph contains duplicate strict states")
    proof_recovered = env.is_proof(state)
    oracle_entails = case.label == "entailed"
    trial = {
        "schema_version": 1,
        "case_id": case.case_id,
        "family_id": case.family_id,
        "condition": case.condition,
        "scc_size": case.scc_size,
        "navigation_variant": navigation_variant,
        "method": method,
        "seed": seed,
        "evidence_status": EVIDENCE_STATUS,
        "environment_signature": env.signature,
        "oracle_entails": oracle_entails,
        "proof_recovered": proof_recovered,
        "task_correct": proof_recovered if oracle_entails else not proof_recovered,
        "circular_false_positive": proof_recovered and not oracle_entails,
        "action_budget": case.action_budget,
        "real_actions": len(real_ledger),
        "real_acquires": sum(row["kind"] == "acquire" for row in real_ledger),
        "real_moves": sum(row["kind"] == "move" for row in real_ledger),
        "unused_real_budget": state.remaining_budget,
        "revealed_source_ids": revealed_source_ids,
        "final_state": state_dict(state),
        "real_ledger": real_ledger,
        "root_choices": planning_trace,
        "closure_trace": closure_trace,
        "simulation_protocol": {
            "simulations_per_decision": simulations_per_decision,
            "transition_cap_per_decision": transition_cap_per_decision,
            "exploration_constant": exploration_constant,
            "counter_rng": "sha256 counter: seed/decision/simulation/depth/state/action/purpose",
            "reward_access": "committed/simulated branch state only; no unrevealed full program",
        },
        "simulation_metrics": {
            "simulations": search.simulations,
            "transitions": search.simulation_transitions,
            "unique_transition_keys": len(search.unique_sim_transition_keys),
            "duplicate_transition_calls": (
                search.simulation_transitions - len(search.unique_sim_transition_keys)
            ),
            "nodes_created_total": search.nodes_created_total,
            "live_nodes_final": len(search.nodes),
            "distinct_live_state_keys": distinct_live_state_keys,
            "duplicate_live_nodes": len(search.nodes) - distinct_live_state_keys,
            "nodes_pruned_total": search.nodes_pruned_total,
            "peak_live_nodes": search.peak_live_nodes,
            "expansions": search.expansions,
            "tt_lookups": search.tt_lookups,
            "tt_hits": search.tt_hits,
            "tt_hit_rate": search.tt_hits / max(1, search.tt_lookups),
            "cross_root_tt_hits": search.cross_root_tt_hits,
            "backprop_updates": search.backprop_updates,
            "simulated_proof_terminals": search.simulated_proof_terminals,
            "selected_child_reuse_decisions": sum(
                item["selected_child_preexisting"] for item in search.rebase_trace
            ),
            "rebase_trace": search.rebase_trace,
        },
        "cross_root_reuse": {
            "selected_child_subtree_reuse_protocol": True,
            "selected_child_reuse_observed": any(
                item["selected_child_preexisting"] for item in search.rebase_trace
            ),
            "selected_child_reuse_decisions": sum(
                item["selected_child_preexisting"] for item in search.rebase_trace
            ),
            "strict_tt_reuse_observed": search.cross_root_tt_hits > 0,
            "strict_tt_cross_root_hits": search.cross_root_tt_hits,
            "interpretation": (
                "Exact Markov states retained below the selected child are reusable. "
                "A zero count means no additional exact MCGS reuse was observed; it "
                "must not be reported as a benefit."
            ),
        },
    }
    validate_online_trial(trial, case.query)
    return trial


def validate_online_trial(trial: Mapping[str, Any], query: a0.Atom) -> None:
    ledger = trial["real_ledger"]
    assert len(ledger) == trial["real_actions"] <= trial["action_budget"]
    acquired: list[str] = []
    previous_closure: set[str] = set()
    for index, row in enumerate(ledger):
        assert row["decision"] == index
        assert row["charged_cost"] == 1
        before = row["state_before"]
        after = row["state_after"]
        assert after["remaining_budget"] == before["remaining_budget"] - 1
        after_closure = set(after["closure"])
        assert previous_closure <= after_closure
        previous_closure = after_closure
        if row["kind"] == "move":
            assert row["revealed_source_id"] is None
            assert row["revealed_formal_payload"] is None
            assert before["acquired_mask"] == after["acquired_mask"]
            assert before["closure"] == after["closure"]
        else:
            assert row["kind"] == "acquire"
            assert row["revealed_source_id"] == before["current_node"]
            assert row["revealed_formal_payload"]
            acquired.append(row["revealed_source_id"])
    assert len(acquired) == len(set(acquired))
    assert acquired == trial["revealed_source_ids"]
    assert trial["proof_recovered"] == (query.text in trial["final_state"]["closure"])
    for planning in trial["root_choices"]:
        assert planning["simulation_transitions"] <= planning["transition_cap"]


def run_unit_invariants(cases: Sequence[a0.BenchmarkCase]) -> dict[str, Any]:
    case = next(
        item
        for item in cases
        if item.scc_size == 3 and item.condition == "productive_seeded_scc"
    )
    canonical = OnlineRevealEnvironment(case, "canonical")
    root = canonical.root()
    acquire = a0.Action("acquire", root.current_node)
    acquired = canonical.transition(root, acquire)
    root_source = canonical.source_map[root.current_node]
    expected = a0.positive_horn_closure(root_source.facts, root_source.rules)
    assert frozenset(acquired.closure) == expected
    assert acquired.acquired_mask.bit_count() == 1
    assert acquired.remaining_budget == root.remaining_budget - 1
    move = next(action for action in canonical.actions(root) if action.kind == "move")
    moved = canonical.transition(root, move)
    assert moved.acquired_mask == root.acquired_mask
    assert moved.closure == root.closure
    assert moved.remaining_budget == root.remaining_budget - 1

    graph = PersistentOnlineSearch(canonical, 17, 1.35, True)
    graph.current_decision = 0
    first = graph._create_or_merge(acquired, created_decision=0)
    second = graph._create_or_merge(acquired, created_decision=0)
    assert first.node_id == second.node_id
    tree = PersistentOnlineSearch(canonical, 17, 1.35, False)
    first_tree = tree._create_or_merge(acquired, created_decision=0)
    second_tree = tree._create_or_merge(acquired, created_decision=0)
    assert first_tree.node_id != second_tree.node_id

    overlay = OnlineRevealEnvironment(case, "bidirectional_chorded_core_overlay")
    core_rules = sorted(
        source.source_id
        for source in case.sources
        if source.source_id.startswith("src_core_rule_")
    )
    assert core_rules[0] in overlay.adjacency[case.root_source_id]
    assert case.root_source_id in overlay.adjacency[core_rules[0]]
    for index, source_id in enumerate(core_rules):
        neighbor = core_rules[(index + 1) % len(core_rules)]
        assert neighbor in overlay.adjacency[source_id]
        assert source_id in overlay.adjacency[neighbor]

    probe_action = canonical.actions(root)[0]
    assert graph._jitter(0, 0, 0, root, probe_action, "probe") == tree._jitter(
        0, 0, 0, root, probe_action, "probe"
    )
    return {
        "status": "passed",
        "case_id": case.case_id,
        "checks": [
            "single acquire reveals exactly the selected source program",
            "move reveals nothing and preserves closure/mask",
            "every real/simulated action decrements budget by one",
            "strict MCGS key merges identical decision-equivalent states",
            "TreeMCTS preserves duplicate state occurrences",
            "overlay root/ring edges are bidirectional",
            "counter RNG is method-independent",
        ],
    }


def select_smoke_cases(
    cases: Sequence[a0.BenchmarkCase],
    sizes: Sequence[int],
    conditions: Sequence[str],
    max_families_per_cell: int,
) -> list[a0.BenchmarkCase]:
    wanted_sizes = set(sizes)
    wanted_conditions = set(conditions)
    grouped: dict[tuple[int, str], list[a0.BenchmarkCase]] = defaultdict(list)
    for case in cases:
        if case.scc_size in wanted_sizes and case.condition in wanted_conditions:
            grouped[(case.scc_size, case.condition)].append(case)
    expected = {(size, condition) for size in wanted_sizes for condition in wanted_conditions}
    if set(grouped) != expected:
        raise ValueError(f"missing requested cells: {sorted(expected - set(grouped))}")
    selected = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda case: case.case_id)
        selected.extend(rows[:max_families_per_cell])
    return selected


def mean(rows: Sequence[Mapping[str, Any]], path: Sequence[str]) -> float:
    values = []
    for row in rows:
        value: Any = row
        for key in path:
            value = value[key]
        values.append(float(value))
    return statistics.mean(values) if values else 0.0


def summarize(trials: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in trials:
        grouped[(
            row["navigation_variant"], row["scc_size"], row["condition"], row["method"]
        )].append(row)
    cells = []
    for (variant, size, condition, method), rows in sorted(grouped.items()):
        positives = [row for row in rows if row["oracle_entails"]]
        cells.append({
            "navigation_variant": variant,
            "scc_size": size,
            "condition": condition,
            "method": method,
            "trials": len(rows),
            "proof_recovery_rate": (
                sum(row["proof_recovered"] for row in positives) / max(1, len(positives))
            ),
            "task_accuracy": sum(row["task_correct"] for row in rows) / len(rows),
            "circular_false_positive_rate": (
                sum(row["circular_false_positive"] for row in rows) / len(rows)
            ),
            "mean_real_actions": mean(rows, ["real_actions"]),
            "mean_real_acquires": mean(rows, ["real_acquires"]),
            "mean_simulation_transitions": mean(rows, ["simulation_metrics", "transitions"]),
            "mean_nodes_created": mean(rows, ["simulation_metrics", "nodes_created_total"]),
            "mean_peak_live_nodes": mean(rows, ["simulation_metrics", "peak_live_nodes"]),
            "mean_tt_hits": mean(rows, ["simulation_metrics", "tt_hits"]),
            "mean_cross_root_tt_hits": mean(
                rows, ["simulation_metrics", "cross_root_tt_hits"]
            ),
        })

    pairs: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in trials:
        pairs[(row["navigation_variant"], row["case_id"], row["seed"])][row["method"]] = row
    paired_rows = []
    for (variant, case_id, seed), methods in sorted(pairs.items()):
        if set(methods) != {"tree_mcts", "mcgs"}:
            raise AssertionError("TreeMCTS/MCGS trial is not paired")
        tree = methods["tree_mcts"]
        graph = methods["mcgs"]
        assert tree["environment_signature"] == graph["environment_signature"]
        assert tree["action_budget"] == graph["action_budget"]
        assert tree["simulation_protocol"] == graph["simulation_protocol"]
        tree_actions = [row["selected_action"] for row in tree["root_choices"]]
        graph_actions = [row["selected_action"] for row in graph["root_choices"]]
        first_action_divergence = next(
            (
                index
                for index in range(max(len(tree_actions), len(graph_actions)))
                if (
                    tree_actions[index] if index < len(tree_actions) else None
                ) != (
                    graph_actions[index] if index < len(graph_actions) else None
                )
            ),
            None,
        )
        paired_rows.append({
            "navigation_variant": variant,
            "case_id": case_id,
            "seed": seed,
            "condition": tree["condition"],
            "scc_size": tree["scc_size"],
            "oracle_entails": tree["oracle_entails"],
            "tree_proof_recovered": tree["proof_recovered"],
            "mcgs_proof_recovered": graph["proof_recovered"],
            "proof_recovery_delta": int(graph["proof_recovered"]) - int(tree["proof_recovered"]),
            "root_action_sequence_changed": tree_actions != graph_actions,
            "first_root_action_divergence_decision": first_action_divergence,
            "node_creation_saving": (
                tree["simulation_metrics"]["nodes_created_total"]
                - graph["simulation_metrics"]["nodes_created_total"]
            ),
            "mcgs_tt_hits": graph["simulation_metrics"]["tt_hits"],
            "mcgs_cross_root_tt_hits": graph["simulation_metrics"]["cross_root_tt_hits"],
        })

    paired_by_size: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in paired_rows:
        paired_by_size[(row["navigation_variant"], row["scc_size"])].append(row)
    by_navigation_and_size = []
    for (variant, size), rows in sorted(paired_by_size.items()):
        positive_rows = [row for row in rows if row["oracle_entails"]]
        total_node_saving = sum(row["node_creation_saving"] for row in rows)
        by_navigation_and_size.append({
            "navigation_variant": variant,
            "scc_size": size,
            "paired_trials": len(rows),
            "positive_paired_trials": len(positive_rows),
            "tree_positive_proof_recovery_rate": (
                sum(row["tree_proof_recovered"] for row in positive_rows)
                / max(1, len(positive_rows))
            ),
            "mcgs_positive_proof_recovery_rate": (
                sum(row["mcgs_proof_recovered"] for row in positive_rows)
                / max(1, len(positive_rows))
            ),
            "node_creation_saving_total": total_node_saving,
            "node_creation_saving_mean": total_node_saving / len(rows),
            "mcgs_tt_hits_total": sum(row["mcgs_tt_hits"] for row in rows),
            "mcgs_cross_root_tt_hits_total": sum(
                row["mcgs_cross_root_tt_hits"] for row in rows
            ),
            "root_action_sequence_changed_pairs": sum(
                row["root_action_sequence_changed"] for row in rows
            ),
            "proof_recovery_changed_pairs": sum(
                row["proof_recovery_delta"] != 0 for row in rows
            ),
        })

    gates = []
    for variant in sorted({row["navigation_variant"] for row in trials}):
        graph_rows = [
            row for row in trials
            if row["navigation_variant"] == variant and row["method"] == "mcgs"
        ]
        hits = sum(row["simulation_metrics"]["tt_hits"] for row in graph_rows)
        cross_root_hits = sum(
            row["simulation_metrics"]["cross_root_tt_hits"] for row in graph_rows
        )
        gates.append({
            "navigation_variant": variant,
            "mcgs_trials": len(graph_rows),
            "tt_hits": hits,
            "cross_root_tt_hits": cross_root_hits,
            "status": (
                "additional_exact_sharing_observed" if hits else "no_exact_sharing_observed"
            ),
            "cross_root_status": (
                "clean_exact_cross_root_reuse_observed"
                if cross_root_hits
                else "no_additional_exact_cross_root_reuse_observed"
            ),
        })
    return {
        "by_cell": cells,
        "by_navigation_and_size": by_navigation_and_size,
        "paired_tree_vs_mcgs": paired_rows,
        "opportunity_gate": gates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--sizes", type=int, nargs="+", default=[3])
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=["productive_seeded_scc", "unseeded_scc", "matched_dag"],
        default=["productive_seeded_scc", "unseeded_scc", "matched_dag"],
    )
    parser.add_argument(
        "--navigation-variants",
        nargs="+",
        choices=list(NAVIGATION_VARIANTS),
        default=list(NAVIGATION_VARIANTS),
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[17])
    parser.add_argument("--max-families-per-cell", type=int, default=1)
    parser.add_argument("--simulations-per-decision", type=int, default=24)
    parser.add_argument("--transition-cap-per-decision", type=int, default=96)
    parser.add_argument("--exploration-constant", type=float, default=1.35)
    parser.add_argument(
        "--allow-non-smoke",
        action="store_true",
        help="Required for more than 24 paired method trials; never implied by defaults.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_families_per_cell <= 0:
        raise ValueError("A1 requires an explicit positive family cap")
    if args.simulations_per_decision <= 0 or args.transition_cap_per_decision <= 0:
        raise ValueError("simulation and transition caps must be positive")
    all_cases = a0.load_cases(args.input)
    invariants = run_unit_invariants(all_cases)
    cases = select_smoke_cases(
        all_cases,
        args.sizes,
        args.conditions,
        args.max_families_per_cell,
    )
    variants = tuple(dict.fromkeys(args.navigation_variants))
    seeds = tuple(sorted(set(args.seeds)))
    trial_count = len(cases) * len(variants) * len(seeds) * len(METHODS)
    if trial_count > 24 and not args.allow_non_smoke:
        raise ValueError(
            f"refusing {trial_count} trials without --allow-non-smoke; default A1 is smoke-only"
        )
    run_mode = "representative_scaling" if trial_count > 24 else "smoke"
    run_id = (
        "a1-online-receding-horizon-representative-scaling-v1"
        if run_mode == "representative_scaling"
        else "a1-online-receding-horizon-smoke-v1"
    )

    started = time.time()
    trials = []
    run_number = 0
    for case in cases:
        for variant in variants:
            for seed in seeds:
                for method, merge_states in METHODS:
                    run_number += 1
                    trial = run_trial(
                        case,
                        variant,
                        method,
                        merge_states,
                        seed,
                        args.simulations_per_decision,
                        args.transition_cap_per_decision,
                        args.exploration_constant,
                    )
                    trials.append(trial)
                    if not args.quiet:
                        metrics = trial["simulation_metrics"]
                        print(
                            f"[{run_number:02d}/{trial_count:02d}] nav={variant:<36} "
                            f"condition={case.condition:<22} method={method:<9} "
                            f"proof={int(trial['proof_recovered'])} real={trial['real_actions']} "
                            f"sim={metrics['transitions']} nodes={metrics['nodes_created_total']} "
                            f"tt={metrics['tt_hits']} cross-root={metrics['cross_root_tt_hits']}",
                            flush=True,
                        )

    summary = summarize(trials)
    limitations = [
        "The oracle simulator returns exact formal outcomes only after a simulated acquire; no parser is tested.",
        "Canonical and overlay results are separate diagnostics; overlay edges are not native data.",
        "Retained node statistics are reusable only because the strict state is deterministic and Markov.",
        "Cross-root MCGS reuse is claimed only when strict_tt_cross_root_hits is positive.",
    ]
    if run_mode == "smoke":
        limitations.append(
            "This smoke has one family, one seed, and size 3; it is not a scaling result."
        )
    else:
        limitations.extend([
            "This representative scaling run fixes one family per size-condition cell and is not exhaustive over all 20 families.",
            "Search and simulator settings were frozen from the preceding smoke; no post-smoke tuning was performed.",
        ])
    results = {
        "schema_version": 1,
        "run_id": run_id,
        "run_status": f"{run_mode}_complete",
        "run_scope": {
            "mode": run_mode,
            "sizes": sorted({case.scc_size for case in cases}),
            "conditions": sorted({case.condition for case in cases}),
            "max_families_per_size_condition": args.max_families_per_cell,
            "selected_case_count": len(cases),
            "method_trial_count": len(trials),
            "exhaustive_over_families": False,
            "post_smoke_tuning": False,
        },
        "evidence_status": EVIDENCE_STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "input": {
            "path": str(args.input.resolve()),
            "sha256": a0.sha256_file(args.input),
            "available_cases": len(all_cases),
            "selected_case_ids": [case.case_id for case in cases],
        },
        "protocol": {
            "one_real_root_action_per_decision": True,
            "replan_from_current_exact_state": True,
            "tree_reuse": "retain selected child's reachable subtree",
            "mcgs_addition": "strict exact-state transposition table",
            "strict_state_key": [
                "current_node", "acquired_mask", "exact_closure", "obligations", "remaining_budget"
            ],
            "unrevealed_formal_access": (
                "none in reward/prior/UCB; oracle payload enters a branch only after acquire"
            ),
            "simulations_per_decision": args.simulations_per_decision,
            "transition_cap_per_decision": args.transition_cap_per_decision,
            "exploration_constant": args.exploration_constant,
            "counter_rng": "method-independent SHA-256 counter RNG",
            "seeds": list(seeds),
            "navigation_variants": list(variants),
        },
        "unit_invariants": invariants,
        "summary": summary,
        "duration_seconds": time.time() - started,
        "limitations": limitations,
    }

    if not args.no_write:
        args.results_dir.mkdir(parents=True, exist_ok=True)
        trials_path = args.results_dir / "a1_online_scaling_trials.jsonl"
        results_path = args.results_dir / "a1_online_scaling_results.json"
        manifest_path = args.results_dir / "a1_online_scaling_manifest.json"
        a0.write_jsonl_atomic(trials_path, trials)
        a0.write_json_atomic(results_path, results)
        manifest = {
            "schema_version": 1,
            "run_id": results["run_id"],
            "run_status": results["run_status"],
            "script": str(SCRIPT_PATH),
            "script_sha256": a0.sha256_file(SCRIPT_PATH),
            "input_sha256": a0.sha256_file(args.input),
            "trials_sha256": a0.sha256_file(trials_path),
            "results_sha256": a0.sha256_file(results_path),
            "trial_count": len(trials),
            "full_run_launched": False,
            "representative_scaling_launched": run_mode == "representative_scaling",
            "unit_invariants": invariants["status"],
        }
        a0.write_json_atomic(manifest_path, manifest)

    print(json.dumps({
        "status": "passed",
        "run_mode": run_mode,
        "trials": len(trials),
        "duration_seconds": time.time() - started,
        "unit_invariants": invariants["status"],
        "opportunity_gate": summary["opportunity_gate"],
        "wrote_results": not args.no_write,
        "results_dir": str(args.results_dir.resolve()),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
