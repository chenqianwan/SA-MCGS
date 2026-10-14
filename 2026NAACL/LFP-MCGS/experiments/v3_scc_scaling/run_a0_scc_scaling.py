#!/usr/bin/env python3
"""Oracle-structure A0: paired TreeMCTS/MCGS on physical SCC navigation.

This runner is deliberately a *diagnostic*, not a confirmatory method result.
It consumes the generated ``data/benchmark.jsonl`` in this directory and uses
the generator's formal fact/rule payloads as deterministic oracle reveals.
There is no LLM, learned outcome model, natural-language parsing claim, or
end-to-end cost claim in this track.

Canonical input fields used by the runner
-----------------------------------------

``case_id, family_id, condition, scc_size, root_source_id, query_atom,
label, sources, source_adjacency, budget``.

Each item in ``sources`` has ``source_id`` and ``formal``.  A formal payload is
one positive-Horn statement:

    {"kind": "fact", "head": {"predicate": "p", "arguments": ["e"]},
     "body": []}

or

    {"kind": "rule", "head": {"predicate": "q", "arguments": ["e"]},
     "body": [{"predicate": "p", "arguments": ["e"]}]}

The physical navigation graph is *only* ``source_adjacency``.  The runner does
not infer edges from source order or text.  At a state, an agent may acquire
the current source (once) or move along one outgoing physical edge.  Both
actions consume one unit of the path budget, so physical SCCs can be revisited
but the finite-horizon search state remains well-defined.

TreeMCTS and MCGS share the environment, rewards, UCB rule, rollout policy,
transition cap, and deterministic common-random-number stream.  Their sole
algorithmic difference is whether nodes with this strict key are merged:

    (current_node, acquired_mask, exact_closure, obligations, remaining_budget)

The main endpoint is oracle proof discovery under a fixed simulator-transition
cap.  Node duplication, strict transposition hits, physical loop/revisit events,
and dead ends are mechanism diagnostics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCRIPT_PATH = Path(__file__).resolve()
EXPERIMENT_ROOT = SCRIPT_PATH.parent
DEFAULT_INPUT = EXPERIMENT_ROOT / "data" / "benchmark.jsonl"
DEFAULT_RESULTS_DIR = EXPERIMENT_ROOT / "results"
REQUIRED_SIZES = (3, 5, 7, 9, 12, 16, 20)
DEFAULT_SEEDS = (17, 29, 43)
NAVIGATION_VARIANTS = ("canonical", "bidirectional_chorded_core_overlay")

EVIDENCE_STATUS = "oracle_structure_diagnostic"
CLAIM_BOUNDARY = (
    "A0 isolates physical-navigation path copying and strict state sharing "
    "under deterministic gold formal reveals. It is not a natural-language, "
    "LLM, learned-simulator, SCC-causality, or end-to-end superiority result."
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_unit(*parts: Any) -> float:
    payload = "|".join(canonical_json(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / 2**64


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


@dataclass(frozen=True, order=True)
class Atom:
    predicate: str
    arguments: tuple[str, ...] = tuple()

    @property
    def text(self) -> str:
        if not self.arguments:
            return self.predicate
        return f"{self.predicate}({','.join(self.arguments)})"


@dataclass(frozen=True)
class HornRule:
    rule_id: str
    body: tuple[Atom, ...]
    head: Atom


@dataclass(frozen=True)
class SourceNode:
    source_id: str
    facts: tuple[Atom, ...]
    rules: tuple[HornRule, ...]
    role: str
    is_distractor: bool


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    family_id: str
    condition: str
    scc_size: int
    actual_recursive_scc_size: int | None
    designed_depth: int | None
    root_source_id: str
    query: Atom
    label: str
    sources: tuple[SourceNode, ...]
    adjacency: Mapping[str, tuple[str, ...]]
    action_budget: int
    generator_gold: Mapping[str, Any]
    raw_pairing: Mapping[str, Any]

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(source.source_id for source in self.sources)

    @property
    def source_map(self) -> dict[str, SourceNode]:
        return {source.source_id: source for source in self.sources}

    @property
    def source_index(self) -> dict[str, int]:
        return {source.source_id: index for index, source in enumerate(self.sources)}


def parse_atom(raw: Any) -> Atom:
    if isinstance(raw, Atom):
        return raw
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            raise ValueError("empty atom string")
        if value.endswith(")") and "(" in value:
            predicate, tail = value[:-1].split("(", 1)
            arguments = tuple(item.strip() for item in tail.split(",") if item.strip())
            return Atom(predicate.strip(), arguments)
        return Atom(value, tuple())
    if not isinstance(raw, Mapping):
        raise ValueError(f"atom must be a string/object, got {raw!r}")
    if "atom" in raw and "predicate" not in raw:
        return parse_atom(raw["atom"])
    predicate = raw.get("predicate")
    arguments = raw.get("arguments", raw.get("args", []))
    if not isinstance(predicate, str) or not predicate.strip():
        raise ValueError(f"invalid atom predicate: {raw!r}")
    if not isinstance(arguments, Sequence) or isinstance(arguments, (str, bytes)):
        raise ValueError(f"invalid atom arguments: {raw!r}")
    return Atom(predicate.strip(), tuple(str(item).strip() for item in arguments))


def parse_formal(source_id: str, raw: Any) -> tuple[tuple[Atom, ...], tuple[HornRule, ...]]:
    payloads = raw if isinstance(raw, list) else [raw]
    facts: list[Atom] = []
    rules: list[HornRule] = []
    for index, payload in enumerate(payloads):
        if not isinstance(payload, Mapping):
            raise ValueError(f"{source_id}: formal payload must be an object")
        kind = str(payload.get("kind", "")).lower()
        head = parse_atom(payload.get("head"))
        body_raw = payload.get("body", [])
        if not isinstance(body_raw, list):
            raise ValueError(f"{source_id}: rule body must be a list")
        body = tuple(sorted((parse_atom(item) for item in body_raw), key=lambda atom: atom.text))
        if kind == "fact":
            if body:
                raise ValueError(f"{source_id}: fact has a non-empty body")
            facts.append(head)
        elif kind == "rule":
            if not body:
                raise ValueError(f"{source_id}: rule has an empty body")
            rules.append(HornRule(f"{source_id}#{index}", body, head))
        else:
            raise ValueError(f"{source_id}: unsupported formal kind {kind!r}")
    return tuple(sorted(set(facts))), tuple(rules)


def positive_horn_closure(facts: Iterable[Atom], rules: Iterable[HornRule]) -> frozenset[Atom]:
    closure = set(facts)
    ordered_rules = tuple(rules)
    changed = True
    while changed:
        changed = False
        for rule in ordered_rules:
            if rule.head not in closure and all(premise in closure for premise in rule.body):
                closure.add(rule.head)
                changed = True
    return frozenset(closure)


def recursive_obligations(
    query: Atom,
    closure: frozenset[Atom],
    rules: Sequence[HornRule],
) -> tuple[Atom, ...]:
    producers: dict[Atom, list[HornRule]] = defaultdict(list)
    for rule in rules:
        producers[rule.head].append(rule)

    def unresolved(atom: Atom, visiting: frozenset[Atom]) -> frozenset[Atom]:
        if atom in closure:
            return frozenset()
        if atom in visiting:
            return frozenset({atom})
        candidates = producers.get(atom, [])
        if not candidates:
            return frozenset({atom})
        alternatives = []
        for rule in candidates:
            missing = frozenset().union(
                *(unresolved(premise, visiting | {atom}) for premise in rule.body)
            )
            alternatives.append(missing)
        return min(alternatives, key=lambda value: (len(value), tuple(item.text for item in sorted(value))))

    return tuple(sorted(unresolved(query, frozenset())))


def load_cases(path: Path) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    seen_case_ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            raw = json.loads(line)
            case_id = str(raw["case_id"])
            if case_id in seen_case_ids:
                raise ValueError(f"duplicate case_id {case_id!r} at line {line_number}")
            seen_case_ids.add(case_id)

            source_rows = raw.get("sources")
            if not isinstance(source_rows, list) or not source_rows:
                raise ValueError(f"{case_id}: sources must be a non-empty list")
            sources: list[SourceNode] = []
            for source_raw in source_rows:
                source_id = str(source_raw["source_id"])
                formal = source_raw.get("formal")
                if formal is None:
                    raise ValueError(f"{case_id}/{source_id}: missing formal oracle payload")
                facts, rules = parse_formal(source_id, formal)
                sources.append(SourceNode(
                    source_id=source_id,
                    facts=facts,
                    rules=rules,
                    role=str(source_raw.get("role", "")),
                    is_distractor=bool(source_raw.get("is_distractor", False)),
                ))
            if len({source.source_id for source in sources}) != len(sources):
                raise ValueError(f"{case_id}: duplicate source IDs")

            source_ids = {source.source_id for source in sources}
            raw_adjacency = raw.get("source_adjacency")
            if not isinstance(raw_adjacency, Mapping):
                raise ValueError(f"{case_id}: source_adjacency must be an object")
            adjacency: dict[str, tuple[str, ...]] = {}
            for source_id in source_ids:
                neighbors_raw = raw_adjacency.get(source_id, [])
                if not isinstance(neighbors_raw, list):
                    raise ValueError(f"{case_id}/{source_id}: adjacency must be a list")
                neighbors = tuple(sorted({str(item) for item in neighbors_raw}))
                unknown = set(neighbors) - source_ids
                if unknown:
                    raise ValueError(f"{case_id}/{source_id}: unknown neighbors {sorted(unknown)}")
                adjacency[source_id] = neighbors

            root_source_id = str(raw["root_source_id"])
            if root_source_id not in source_ids:
                raise ValueError(f"{case_id}: root_source_id is absent from sources")
            budget_raw = raw.get("budget", {})
            if not isinstance(budget_raw, Mapping):
                raise ValueError(f"{case_id}: budget must be an object")
            action_budget = int(budget_raw.get("real_action_budget", 2 * (int(raw["scc_size"]) + 1)))
            if action_budget <= 0:
                raise ValueError(f"{case_id}: action budget must be positive")

            case = BenchmarkCase(
                case_id=case_id,
                family_id=str(raw.get("family_id", case_id)),
                condition=str(raw["condition"]),
                scc_size=int(raw["scc_size"]),
                actual_recursive_scc_size=(
                    int(raw["actual_recursive_scc_size"])
                    if raw.get("actual_recursive_scc_size") is not None
                    else None
                ),
                designed_depth=(int(raw["designed_depth"]) if raw.get("designed_depth") is not None else None),
                root_source_id=root_source_id,
                query=parse_atom(raw["query_atom"]),
                label=str(raw.get("label", "")).lower(),
                sources=tuple(sources),
                adjacency=adjacency,
                action_budget=action_budget,
                generator_gold=raw.get("gold", {}),
                raw_pairing=raw.get("pairing", {}),
            )
            _validate_case_oracle(case)
            cases.append(case)
    if not cases:
        raise ValueError(f"no benchmark rows found in {path}")
    return cases


def _validate_case_oracle(case: BenchmarkCase) -> None:
    facts = [fact for source in case.sources for fact in source.facts]
    rules = [rule for source in case.sources for rule in source.rules]
    closure = positive_horn_closure(facts, rules)
    entails = case.query in closure
    if case.label not in {"entailed", "unknown"}:
        raise ValueError(f"{case.case_id}: unsupported label {case.label!r}")
    if entails != (case.label == "entailed"):
        raise AssertionError(
            f"{case.case_id}: independent LFP entails={entails} but label={case.label}"
        )
    gold_entails = case.generator_gold.get("query_entailed")
    if gold_entails is not None and bool(gold_entails) != entails:
        raise AssertionError(f"{case.case_id}: generator gold query_entailed mismatch")
    raw_gold_closure = case.generator_gold.get("closure_atoms")
    if isinstance(raw_gold_closure, list):
        gold_closure = frozenset(parse_atom(item) for item in raw_gold_closure)
        if gold_closure != closure:
            missing = sorted(atom.text for atom in gold_closure - closure)[:5]
            extra = sorted(atom.text for atom in closure - gold_closure)[:5]
            raise AssertionError(
                f"{case.case_id}: independent/generator closure mismatch; missing={missing}, extra={extra}"
            )

    reference_cost = reference_proof_action_cost(case)
    if entails:
        if reference_cost is None:
            raise AssertionError(f"{case.case_id}: entailed case has no navigable gold proof route")
        if reference_cost > case.action_budget:
            raise AssertionError(
                f"{case.case_id}: gold proof route costs {reference_cost} actions "
                f"but budget is {case.action_budget}"
            )


def shortest_directed_distance(
    adjacency: Mapping[str, tuple[str, ...]],
    start: str,
    target: str,
) -> int | None:
    """Return the unweighted directed distance without relying on source order."""

    pending: deque[tuple[str, int]] = deque([(start, 0)])
    seen = {start}
    while pending:
        node, distance = pending.popleft()
        if node == target:
            return distance
        for neighbor in adjacency[node]:
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append((neighbor, distance + 1))
    return None


def reference_proof_action_cost(case: BenchmarkCase) -> int | None:
    """Cost the generator's ordered gold proof route on canonical navigation.

    This is a feasibility audit only.  The search policy never receives or uses
    the gold source list.  Each proof source costs one acquire action; travel
    between consecutive proof sources is charged by canonical directed shortest
    path.  Unknown cases intentionally have no reference proof route.
    """

    raw_source_ids = case.generator_gold.get("proof_source_ids", [])
    if not isinstance(raw_source_ids, list):
        raise ValueError(f"{case.case_id}: gold.proof_source_ids must be a list")
    if not raw_source_ids:
        return None
    proof_source_ids = tuple(str(source_id) for source_id in raw_source_ids)
    unknown = set(proof_source_ids) - set(case.source_ids)
    if unknown:
        raise ValueError(f"{case.case_id}: gold proof uses unknown sources {sorted(unknown)}")

    acquired_facts: list[Atom] = []
    acquired_rules: list[HornRule] = []
    source_map = case.source_map
    current = case.root_source_id
    cost = 0
    for target in proof_source_ids:
        distance = shortest_directed_distance(case.adjacency, current, target)
        if distance is None:
            return None
        cost += distance + 1
        source = source_map[target]
        acquired_facts.extend(source.facts)
        acquired_rules.extend(source.rules)
        current = target
    if case.query not in positive_horn_closure(acquired_facts, acquired_rules):
        raise AssertionError(f"{case.case_id}: gold proof sources do not entail the query")
    return cost


@dataclass(frozen=True)
class NavigationState:
    current_node: str
    acquired_mask: int
    closure: tuple[Atom, ...]
    obligations: tuple[Atom, ...]
    remaining_budget: int

    @property
    def key(self) -> tuple[Any, ...]:
        return (
            self.current_node,
            self.acquired_mask,
            tuple(atom.text for atom in self.closure),
            tuple(atom.text for atom in self.obligations),
            self.remaining_budget,
        )


@dataclass(frozen=True, order=True)
class Action:
    kind: str
    target: str

    @property
    def text(self) -> str:
        return f"{self.kind}:{self.target}"


class OracleNavigationEnvironment:
    """Deterministic gold-reveal environment for one generated case."""

    def __init__(self, case: BenchmarkCase, navigation_variant: str):
        if navigation_variant not in NAVIGATION_VARIANTS:
            raise ValueError(f"unknown navigation variant {navigation_variant!r}")
        self.case = case
        self.navigation_variant = navigation_variant
        self.source_map = case.source_map
        self.source_index = case.source_index
        self.adjacency = self._build_adjacency(navigation_variant)
        self._summary_cache: dict[int, tuple[tuple[Atom, ...], tuple[Atom, ...]]] = {}
        all_facts = [fact for source in case.sources for fact in source.facts]
        all_rules = [rule for source in case.sources for rule in source.rules]
        self.full_closure = positive_horn_closure(all_facts, all_rules)
        self.oracle_entails = case.query in self.full_closure
        self.relevant_atoms = self._query_ancestor_cone(tuple(all_rules)) & self.full_closure

    def _build_adjacency(self, navigation_variant: str) -> dict[str, tuple[str, ...]]:
        if navigation_variant == "canonical":
            return {source_id: tuple(neighbors) for source_id, neighbors in self.case.adjacency.items()}

        # Stress-only overlay.  The generated canonical graph is deliberately
        # retained, then the same source-ID-defined bidirectional ring/chords
        # are added in every semantic condition.  This creates exact merge
        # opportunities without inspecting fact/rule predicates or gold proof
        # membership.  It is never reported as native benchmark structure.
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
            raise ValueError(f"{self.case.case_id}: overlay requires src_core_rule_* nodes")

        def connect_bidirectional(left: str, right: str) -> None:
            if left == right:
                return
            adjacency[left].add(right)
            adjacency[right].add(left)

        connect_bidirectional(self.case.root_source_id, core_rules[0])
        if len(core_rules) > 1:
            for index, source_id in enumerate(core_rules):
                connect_bidirectional(source_id, core_rules[(index + 1) % len(core_rules)])
        if len(core_rules) >= 4:
            for index, source_id in enumerate(core_rules):
                connect_bidirectional(source_id, core_rules[(index + 2) % len(core_rules)])
        return {
            source_id: tuple(sorted(neighbors))
            for source_id, neighbors in adjacency.items()
        }

    def _query_ancestor_cone(self, rules: Sequence[HornRule]) -> frozenset[Atom]:
        producers: dict[Atom, list[HornRule]] = defaultdict(list)
        for rule in rules:
            producers[rule.head].append(rule)
        relevant = {self.case.query}
        pending = [self.case.query]
        while pending:
            atom = pending.pop()
            for rule in producers.get(atom, []):
                for premise in rule.body:
                    if premise not in relevant:
                        relevant.add(premise)
                        pending.append(premise)
        return frozenset(relevant)

    def _program_for_mask(self, mask: int) -> tuple[list[Atom], list[HornRule]]:
        facts: list[Atom] = []
        rules: list[HornRule] = []
        for index, source in enumerate(self.case.sources):
            if mask & (1 << index):
                facts.extend(source.facts)
                rules.extend(source.rules)
        return facts, rules

    def _summarize_mask(self, mask: int) -> tuple[tuple[Atom, ...], tuple[Atom, ...]]:
        cached = self._summary_cache.get(mask)
        if cached is not None:
            return cached
        facts, rules = self._program_for_mask(mask)
        closure = positive_horn_closure(facts, rules)
        obligations = recursive_obligations(self.case.query, closure, rules)
        summary = (tuple(sorted(closure)), obligations)
        self._summary_cache[mask] = summary
        return summary

    def make_state(self, current_node: str, acquired_mask: int, remaining_budget: int) -> NavigationState:
        closure, obligations = self._summarize_mask(acquired_mask)
        return NavigationState(current_node, acquired_mask, closure, obligations, remaining_budget)

    def root(self) -> NavigationState:
        return self.make_state(self.case.root_source_id, 0, self.case.action_budget)

    def is_proof(self, state: NavigationState) -> bool:
        return self.case.query in state.closure

    def actions(self, state: NavigationState) -> tuple[Action, ...]:
        if state.remaining_budget <= 0 or self.is_proof(state):
            return tuple()
        actions: list[Action] = []
        index = self.source_index[state.current_node]
        if not state.acquired_mask & (1 << index):
            actions.append(Action("acquire", state.current_node))
        actions.extend(Action("move", neighbor) for neighbor in self.adjacency[state.current_node])
        return tuple(sorted(actions))

    def action_prior(self, state: NavigationState, action: Action) -> float:
        if action.kind == "acquire":
            return 1.0
        target_index = self.source_index[action.target]
        target_unseen = not state.acquired_mask & (1 << target_index)
        return 0.62 if target_unseen else 0.20

    def transition(self, state: NavigationState, action: Action) -> NavigationState:
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
            return self.make_state(action.target, state.acquired_mask, state.remaining_budget - 1)
        raise ValueError(action.kind)

    def reward(self, state: NavigationState) -> float:
        if self.is_proof(state):
            efficiency = state.remaining_budget / max(1, self.case.action_budget)
            return 1.0 + 0.05 * efficiency
        relevant_denominator = max(1, len(self.relevant_atoms))
        progress = len(set(state.closure) & self.relevant_atoms) / relevant_denominator
        obligation_score = 1.0 / (1.0 + len(state.obligations))
        acquired_ratio = state.acquired_mask.bit_count() / max(1, len(self.case.sources))
        return 0.66 * progress + 0.20 * obligation_score + 0.09 * acquired_ratio


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
    state: NavigationState
    visits: int = 0
    value_sum: float = 0.0
    edges: dict[Action, EdgeStats] = field(default_factory=dict)


class PairedMonteCarloSearch:
    """One implementation; ``merge_states`` is the only Tree/Graph switch."""

    def __init__(
        self,
        environment: OracleNavigationEnvironment,
        seed: int,
        transition_cap: int,
        exploration_constant: float,
        merge_states: bool,
    ):
        self.env = environment
        self.seed = seed
        self.transition_cap = transition_cap
        self.exploration_constant = exploration_constant
        self.merge_states = merge_states
        self.nodes: dict[str, SearchNode] = {}
        self.state_index: dict[tuple[Any, ...], str] = {}
        self.next_node_id = 0

        self.transitions = 0
        self.expansions = 0
        self.tt_lookups = 0
        self.tt_hits = 0
        self.backprop_updates = 0
        self.simulations = 0
        self.loop_transitions = 0
        self.loop_simulations = 0
        self.acquired_node_revisits = 0
        self.physical_dead_end_simulations = 0
        self.budget_exhausted_simulations = 0
        self.proof_terminal_simulations = 0
        self.unique_transition_keys: set[tuple[Any, ...]] = set()
        self.first_proof_transition: int | None = None
        self.best_state: NavigationState | None = None
        self.best_reward = -math.inf
        self.max_closure_size = 0
        self.max_depth = 0

    def _create_or_merge(self, state: NavigationState) -> SearchNode:
        if self.merge_states:
            self.tt_lookups += 1
            existing_id = self.state_index.get(state.key)
            if existing_id is not None:
                existing = self.nodes[existing_id]
                if existing.state != state or self.env.actions(existing.state) != self.env.actions(state):
                    raise AssertionError("strict-key transposition is not decision equivalent")
                self.tt_hits += 1
                return existing
        node_id = f"n{self.next_node_id}"
        self.next_node_id += 1
        node = SearchNode(node_id, state)
        self.nodes[node_id] = node
        if self.merge_states:
            self.state_index[state.key] = node_id
        return node

    def _jitter(self, simulation: int, depth: int, state: NavigationState, action: Action) -> float:
        return stable_unit(self.seed, simulation, depth, state.key, action.text)

    def _choose_unexpanded(
        self,
        actions: Sequence[Action],
        state: NavigationState,
        simulation: int,
        depth: int,
    ) -> Action:
        return max(
            actions,
            key=lambda action: (
                self.env.action_prior(state, action),
                self._jitter(simulation, depth, state, action),
                action.text,
            ),
        )

    def _choose_ucb(self, node: SearchNode, simulation: int, depth: int) -> Action:
        log_parent = math.log(max(2, node.visits + 1))
        return max(
            node.edges,
            key=lambda action: (
                node.edges[action].q
                + self.exploration_constant
                * self.env.action_prior(node.state, action)
                * math.sqrt(log_parent / (1 + node.edges[action].visits)),
                self._jitter(simulation, depth, node.state, action),
                action.text,
            ),
        )

    def _choose_rollout(
        self,
        state: NavigationState,
        simulation: int,
        depth: int,
    ) -> Action:
        actions = self.env.actions(state)
        return max(
            actions,
            key=lambda action: (
                self.env.action_prior(state, action)
                + 0.35 * self._jitter(simulation, depth, state, action),
                action.text,
            ),
        )

    def _observe_state(self, state: NavigationState) -> None:
        reward = self.env.reward(state)
        if reward > self.best_reward:
            self.best_reward = reward
            self.best_state = state
        self.max_closure_size = max(self.max_closure_size, len(state.closure))
        if self.env.is_proof(state) and self.first_proof_transition is None:
            self.first_proof_transition = self.transitions

    def _step(
        self,
        state: NavigationState,
        action: Action,
        physical_history: list[str],
    ) -> tuple[NavigationState, bool]:
        if self.transitions >= self.transition_cap:
            raise RuntimeError("transition cap exceeded")
        transition_key = (state.key, action.text)
        successor = self.env.transition(state, action)
        self.transitions += 1
        self.unique_transition_keys.add(transition_key)
        looped = False
        if action.kind == "move":
            if successor.current_node in physical_history:
                self.loop_transitions += 1
                looped = True
            target_index = self.env.source_index[successor.current_node]
            if successor.acquired_mask & (1 << target_index):
                self.acquired_node_revisits += 1
            physical_history.append(successor.current_node)
        self._observe_state(successor)
        return successor, looped

    def _record_terminal(self, state: NavigationState) -> None:
        if self.env.is_proof(state):
            self.proof_terminal_simulations += 1
        elif state.remaining_budget <= 0:
            self.budget_exhausted_simulations += 1
        elif not self.env.actions(state):
            self.physical_dead_end_simulations += 1

    def run(self) -> dict[str, Any]:
        root = self._create_or_merge(self.env.root())
        self._observe_state(root.state)
        if not self.env.actions(root.state):
            self._record_terminal(root.state)
        stagnant_simulations = 0

        while self.transitions < self.transition_cap and self.env.actions(root.state):
            simulation = self.simulations
            self.simulations += 1
            node = root
            path_nodes = [root]
            path_edges: list[tuple[SearchNode, Action]] = []
            physical_history = [root.state.current_node]
            depth = 0
            looped_in_simulation = False
            transition_at_start = self.transitions
            expanded = False

            while self.transitions < self.transition_cap:
                actions = self.env.actions(node.state)
                if not actions:
                    break
                unexpanded = [action for action in actions if action not in node.edges]
                if unexpanded:
                    action = self._choose_unexpanded(unexpanded, node.state, simulation, depth)
                    successor, looped = self._step(node.state, action, physical_history)
                    looped_in_simulation = looped_in_simulation or looped
                    child = self._create_or_merge(successor)
                    node.edges[action] = EdgeStats(child.node_id)
                    self.expansions += 1
                    path_edges.append((node, action))
                    node = child
                    path_nodes.append(node)
                    depth += 1
                    expanded = True
                    self.max_depth = max(self.max_depth, depth)
                    break

                action = self._choose_ucb(node, simulation, depth)
                successor, looped = self._step(node.state, action, physical_history)
                looped_in_simulation = looped_in_simulation or looped
                child = self.nodes[node.edges[action].child_id]
                if successor != child.state:
                    raise AssertionError("stored edge disagrees with exact transition")
                path_edges.append((node, action))
                node = child
                path_nodes.append(node)
                depth += 1
                self.max_depth = max(self.max_depth, depth)

            final_state = node.state
            if expanded and self.transitions < self.transition_cap:
                while self.transitions < self.transition_cap:
                    actions = self.env.actions(final_state)
                    if not actions:
                        break
                    action = self._choose_rollout(final_state, simulation, depth)
                    final_state, looped = self._step(final_state, action, physical_history)
                    looped_in_simulation = looped_in_simulation or looped
                    depth += 1
                    self.max_depth = max(self.max_depth, depth)

            reward = self.env.reward(final_state)
            for visited in path_nodes:
                visited.visits += 1
                visited.value_sum += reward
                self.backprop_updates += 1
            for parent, action in path_edges:
                parent.edges[action].visits += 1
                parent.edges[action].value_sum += reward
            if looped_in_simulation:
                self.loop_simulations += 1
            self._record_terminal(final_state)

            if self.transitions == transition_at_start:
                stagnant_simulations += 1
                if stagnant_simulations >= 2:
                    break
            else:
                stagnant_simulations = 0

        distinct_state_keys = len({node.state.key for node in self.nodes.values()})
        best_state = self.best_state or root.state
        proof_recovered = self.first_proof_transition is not None
        oracle_entails = self.env.oracle_entails
        reference_cost = reference_proof_action_cost(self.env.case)
        return {
            "case_id": self.env.case.case_id,
            "family_id": self.env.case.family_id,
            "condition": self.env.case.condition,
            "navigation_variant": self.env.navigation_variant,
            "scc_size": self.env.case.scc_size,
            "actual_recursive_scc_size": self.env.case.actual_recursive_scc_size,
            "designed_depth": self.env.case.designed_depth,
            "method": "mcgs" if self.merge_states else "tree_mcts",
            "seed": self.seed,
            "evidence_status": EVIDENCE_STATUS,
            "oracle_entails": oracle_entails,
            "proof_recovered": proof_recovered,
            "task_correct": proof_recovered if oracle_entails else not proof_recovered,
            "circular_false_positive": proof_recovered and not oracle_entails,
            "first_proof_transition": self.first_proof_transition,
            "transition_cap": self.transition_cap,
            "transitions": self.transitions,
            "unique_transition_keys": len(self.unique_transition_keys),
            "duplicate_transition_calls": self.transitions - len(self.unique_transition_keys),
            "simulations": self.simulations,
            "nodes": len(self.nodes),
            "distinct_state_keys": distinct_state_keys,
            "duplicate_nodes": len(self.nodes) - distinct_state_keys,
            "expansions": self.expansions,
            "tt_lookups": self.tt_lookups,
            "tt_hits": self.tt_hits,
            "tt_hit_rate": self.tt_hits / max(1, self.tt_lookups),
            "backprop_updates": self.backprop_updates,
            "loop_transitions": self.loop_transitions,
            "loop_simulations": self.loop_simulations,
            "loop_simulation_rate": self.loop_simulations / max(1, self.simulations),
            "acquired_node_revisits": self.acquired_node_revisits,
            "physical_dead_end_simulations": self.physical_dead_end_simulations,
            "budget_exhausted_simulations": self.budget_exhausted_simulations,
            "proof_terminal_simulations": self.proof_terminal_simulations,
            "max_depth": self.max_depth,
            "max_closure_size": self.max_closure_size,
            "best_reward": self.best_reward,
            "best_remaining_budget": best_state.remaining_budget,
            "best_acquired_count": best_state.acquired_mask.bit_count(),
            "action_budget": self.env.case.action_budget,
            "reference_proof_action_cost": reference_cost,
            "reference_budget_slack": (
                self.env.case.action_budget - reference_cost
                if reference_cost is not None
                else None
            ),
            "source_count": len(self.env.case.sources),
            "search_exhausted_before_cap": self.transitions < self.transition_cap,
        }


def mean(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / max(1, len(rows))


def summarize_trials(trials: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in trials:
        grouped[(
            row["navigation_variant"],
            row["scc_size"],
            row["condition"],
            row["method"],
        )].append(row)

    by_cell = []
    for (navigation_variant, size, condition, method), rows in sorted(grouped.items()):
        positives = [row for row in rows if row["oracle_entails"]]
        reference_costs = [
            row["reference_proof_action_cost"]
            for row in positives
            if row["reference_proof_action_cost"] is not None
        ]
        reference_slacks = [
            row["reference_budget_slack"]
            for row in positives
            if row["reference_budget_slack"] is not None
        ]
        proof_transitions = [
            row["first_proof_transition"]
            for row in positives
            if row["first_proof_transition"] is not None
        ]
        by_cell.append({
            "navigation_variant": navigation_variant,
            "scc_size": size,
            "condition": condition,
            "method": method,
            "trials": len(rows),
            "oracle_positive_trials": len(positives),
            "proof_recovery_rate": (
                sum(bool(row["proof_recovered"]) for row in positives) / max(1, len(positives))
            ),
            "task_accuracy": sum(bool(row["task_correct"]) for row in rows) / len(rows),
            "circular_false_positive_rate": (
                sum(bool(row["circular_false_positive"]) for row in rows) / len(rows)
            ),
            "mean_first_proof_transition": (
                statistics.mean(proof_transitions) if proof_transitions else None
            ),
            "mean_reference_proof_action_cost": (
                statistics.mean(reference_costs) if reference_costs else None
            ),
            "min_reference_budget_slack": min(reference_slacks) if reference_slacks else None,
            "mean_nodes": mean(rows, "nodes"),
            "mean_distinct_state_keys": mean(rows, "distinct_state_keys"),
            "mean_duplicate_nodes": mean(rows, "duplicate_nodes"),
            "mean_transitions": mean(rows, "transitions"),
            "mean_duplicate_transition_calls": mean(rows, "duplicate_transition_calls"),
            "mean_tt_hits": mean(rows, "tt_hits"),
            "mean_tt_hit_rate": mean(rows, "tt_hit_rate"),
            "mean_loop_transitions": mean(rows, "loop_transitions"),
            "mean_loop_simulation_rate": mean(rows, "loop_simulation_rate"),
            "mean_acquired_node_revisits": mean(rows, "acquired_node_revisits"),
            "mean_physical_dead_ends": mean(rows, "physical_dead_end_simulations"),
            "mean_budget_exhaustions": mean(rows, "budget_exhausted_simulations"),
            "mean_max_depth": mean(rows, "max_depth"),
            "mean_max_closure_size": mean(rows, "max_closure_size"),
        })

    paired: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in trials:
        paired[(row["navigation_variant"], row["case_id"], row["seed"])][row["method"]] = row
    paired_rows = []
    for ((_navigation_variant, _case_id, _seed), methods) in sorted(paired.items()):
        if set(methods) != {"tree_mcts", "mcgs"}:
            raise AssertionError("unpaired TreeMCTS/MCGS trial")
        tree = methods["tree_mcts"]
        graph = methods["mcgs"]
        if tree["transitions"] != graph["transitions"] and not (
            tree["search_exhausted_before_cap"] or graph["search_exhausted_before_cap"]
        ):
            raise AssertionError("paired methods did not receive the same transition cap")
        paired_rows.append({
            "navigation_variant": tree["navigation_variant"],
            "case_id": tree["case_id"],
            "seed": tree["seed"],
            "scc_size": tree["scc_size"],
            "condition": tree["condition"],
            "node_saving_rate": 1.0 - graph["nodes"] / max(1, tree["nodes"]),
            "duplicate_node_reduction": tree["duplicate_nodes"] - graph["duplicate_nodes"],
            "mcgs_tt_hits": graph["tt_hits"],
            "proof_recovery_delta": int(graph["proof_recovered"]) - int(tree["proof_recovered"]),
            "loop_transition_delta": graph["loop_transitions"] - tree["loop_transitions"],
            "dead_end_delta": (
                graph["physical_dead_end_simulations"] - tree["physical_dead_end_simulations"]
            ),
        })

    paired_grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in paired_rows:
        paired_grouped[(row["navigation_variant"], row["scc_size"], row["condition"])].append(row)
    paired_by_cell = []
    for (navigation_variant, size, condition), rows in sorted(paired_grouped.items()):
        paired_by_cell.append({
            "navigation_variant": navigation_variant,
            "scc_size": size,
            "condition": condition,
            "pairs": len(rows),
            "mean_node_saving_rate": mean(rows, "node_saving_rate"),
            "mean_duplicate_node_reduction": mean(rows, "duplicate_node_reduction"),
            "mean_mcgs_tt_hits": mean(rows, "mcgs_tt_hits"),
            "mean_proof_recovery_delta": mean(rows, "proof_recovery_delta"),
            "mean_loop_transition_delta": mean(rows, "loop_transition_delta"),
            "mean_dead_end_delta": mean(rows, "dead_end_delta"),
        })
    opportunity_gate = []
    for navigation_variant in sorted({row["navigation_variant"] for row in trials}):
        graph_rows = [
            row for row in trials
            if row["navigation_variant"] == navigation_variant and row["method"] == "mcgs"
        ]
        total_hits = sum(row["tt_hits"] for row in graph_rows)
        total_lookups = sum(row["tt_lookups"] for row in graph_rows)
        trials_with_hits = sum(row["tt_hits"] > 0 for row in graph_rows)
        trial_coverage = trials_with_hits / max(1, len(graph_rows))
        lookup_hit_rate = total_hits / max(1, total_lookups)
        if total_hits == 0:
            status = "no_go_zero_exact_transpositions"
        elif trial_coverage < 0.10 or lookup_hit_rate < 0.01:
            status = "no_go_sparse_exact_transpositions"
        else:
            status = "opportunity_present"
        opportunity_gate.append({
            "navigation_variant": navigation_variant,
            "mcgs_trials": len(graph_rows),
            "mcgs_trials_with_tt_hits": trials_with_hits,
            "trial_coverage_with_tt_hits": trial_coverage,
            "total_tt_lookups": total_lookups,
            "total_tt_hits": total_hits,
            "aggregate_tt_hit_rate": lookup_hit_rate,
            "gate_rule": (
                "NO-GO if zero hits, or if fewer than 10% of trials have a hit, "
                "or aggregate strict-key hit rate is below 1%"
            ),
            "status": status,
        })
    return {
        "by_size_condition_method": by_cell,
        "paired_tree_vs_mcgs": paired_by_cell,
        "transposition_opportunity_gate": opportunity_gate,
    }


def select_cases(
    cases: Sequence[BenchmarkCase],
    sizes: Sequence[int],
    max_cases_per_cell: int,
) -> list[BenchmarkCase]:
    wanted = set(sizes)
    filtered = [case for case in cases if case.scc_size in wanted]
    present = {case.scc_size for case in filtered}
    missing = wanted - present
    if missing:
        raise ValueError(f"input is missing requested SCC sizes: {sorted(missing)}")
    if max_cases_per_cell <= 0:
        return sorted(filtered, key=lambda case: (case.scc_size, case.condition, case.case_id))
    grouped: dict[tuple[int, str], list[BenchmarkCase]] = defaultdict(list)
    for case in filtered:
        grouped[(case.scc_size, case.condition)].append(case)
    selected = []
    for key in sorted(grouped):
        selected.extend(sorted(grouped[key], key=lambda case: case.case_id)[:max_cases_per_cell])
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--sizes", type=int, nargs="+", default=list(REQUIRED_SIZES))
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--transition-cap", type=int, default=2048)
    parser.add_argument("--exploration-constant", type=float, default=1.35)
    parser.add_argument(
        "--navigation-variants",
        nargs="+",
        choices=list(NAVIGATION_VARIANTS),
        default=list(NAVIGATION_VARIANTS),
        help=(
            "canonical is the generated graph; bidirectional_chorded_core_overlay "
            "is an explicitly synthetic merge-opportunity stress diagnostic."
        ),
    )
    parser.add_argument(
        "--max-cases-per-cell",
        type=int,
        default=0,
        help="0 runs every generated case; a positive value selects a deterministic smoke prefix.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress one-line per-trial progress (the final aggregate table is still printed).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if len(set(args.seeds)) < 3:
        raise ValueError("A0 requires at least three distinct paired seeds")
    if args.transition_cap <= 0:
        raise ValueError("transition cap must be positive")
    if not args.input.exists():
        raise FileNotFoundError(
            f"generated benchmark not found: {args.input}. "
            "Run the sibling SCC benchmark generator first."
        )

    started = time.time()
    all_cases = load_cases(args.input)
    cases = select_cases(all_cases, args.sizes, args.max_cases_per_cell)
    trials: list[dict[str, Any]] = []
    navigation_variants = tuple(dict.fromkeys(args.navigation_variants))
    total_runs = len(cases) * len(set(args.seeds)) * 2 * len(navigation_variants)
    run_number = 0
    for case in cases:
        for navigation_variant in navigation_variants:
            for seed in sorted(set(args.seeds)):
                for method, merge_states in (("tree_mcts", False), ("mcgs", True)):
                    run_number += 1
                    environment = OracleNavigationEnvironment(case, navigation_variant)
                    search = PairedMonteCarloSearch(
                        environment=environment,
                        seed=seed,
                        transition_cap=args.transition_cap,
                        exploration_constant=args.exploration_constant,
                        merge_states=merge_states,
                    )
                    row = search.run()
                    trials.append(row)
                    if not args.quiet:
                        print(
                            f"[{run_number:04d}/{total_runs:04d}] nav={navigation_variant:<36} "
                            f"size={case.scc_size:>2} condition={case.condition:<18} "
                            f"{method:<9} seed={seed:<3} proof={int(row['proof_recovered'])} "
                            f"nodes={row['nodes']:<5} tt={row['tt_hits']:<5} "
                            f"loops={row['loop_transitions']}",
                            flush=True,
                        )

    summaries = summarize_trials(trials)
    run_id = f"a0-oracle-structure-{int(started)}"
    results = {
        "schema_version": 1,
        "run_id": run_id,
        "run_status": "complete",
        "evidence_status": EVIDENCE_STATUS,
        "claim_boundary": CLAIM_BOUNDARY,
        "input": {
            "path": str(args.input.resolve()),
            "sha256": sha256_file(args.input),
            "available_cases": len(all_cases),
            "selected_cases": len(cases),
            "conditions": sorted({case.condition for case in cases}),
            "sizes": sorted({case.scc_size for case in cases}),
        },
        "protocol": {
            "formal_reveal": "deterministic generator gold; no LLM",
            "physical_graph": (
                "canonical uses source_adjacency; bidirectional_chorded_core_overlay retains "
                "it and adds the explicitly synthetic, condition-shared core overlay"
            ),
            "actions": "acquire current source once OR move along one directed physical edge",
            "path_budget": "generator budget.real_action_budget; both move and acquire cost one",
            "budget_feasibility_audit": (
                "gold proof_source_ids are used only after loading to verify a canonical directed "
                "reference route fits the budget; they are never exposed to the search policy"
            ),
            "state_key": [
                "current_node",
                "acquired_mask",
                "exact_closure",
                "obligations",
                "remaining_budget",
            ],
            "paired_methods": "same implementation; only strict state merging is toggled",
            "transition_cap": args.transition_cap,
            "exploration_constant": args.exploration_constant,
            "seeds": sorted(set(args.seeds)),
            "navigation_variants": list(navigation_variants),
            "max_cases_per_cell": args.max_cases_per_cell,
        },
        "summary": summaries,
        "duration_seconds": time.time() - started,
        "limitations": [
            "Oracle formal payloads and oracle source adjacency are available to the simulator.",
            "Proof recovery means a proof state was discovered during capped search, not live root-action execution.",
            "This track isolates physical-navigation path copying and strict transpositions; it does not test natural-language parsing.",
            "MCGS merging is within one capped search; this runner does not claim live subtree reuse or token savings.",
            "The bidirectional/chorded overlay is a runner-generated opportunity stress and is not native benchmark structure.",
            "The sparse-transposition NO-GO cutoff is a diagnostic reporting convention, not a preregistered confirmatory threshold.",
            "Any SCC-versus-control causal claim depends on the generator's matched construction and belongs to a later confirmatory protocol.",
        ],
    }

    args.results_dir.mkdir(parents=True, exist_ok=True)
    trials_path = args.results_dir / "a0_oracle_structure_trials.jsonl"
    results_path = args.results_dir / "a0_oracle_structure_results.json"
    manifest_path = args.results_dir / "a0_oracle_structure_manifest.json"
    write_jsonl_atomic(trials_path, trials)
    write_json_atomic(results_path, results)
    manifest = {
        "run_id": run_id,
        "created_unix": time.time(),
        "evidence_status": EVIDENCE_STATUS,
        "inputs": {
            "benchmark": {"path": str(args.input.resolve()), "sha256": sha256_file(args.input)},
            "runner": {"path": str(SCRIPT_PATH), "sha256": sha256_file(SCRIPT_PATH)},
        },
        "outputs": {
            "trials": {"path": str(trials_path.resolve()), "sha256": sha256_file(trials_path)},
            "results": {"path": str(results_path.resolve()), "sha256": sha256_file(results_path)},
        },
        "python": {"version": platform.python_version(), "platform": platform.platform()},
    }
    write_json_atomic(manifest_path, manifest)

    print("\nA0 oracle-structure summary")
    print("navigation                           size condition           method     recovery  nodes    transitions  tt_hits  loop_rate  dead_ends")
    for row in summaries["by_size_condition_method"]:
        print(
            f"{row['navigation_variant']:<36} {row['scc_size']:>4} "
            f"{row['condition']:<19} {row['method']:<10} "
            f"{row['proof_recovery_rate']:.3f}    {row['mean_nodes']:>7.1f} "
            f"{row['mean_transitions']:>11.1f} {row['mean_tt_hits']:>8.1f} "
            f"{row['mean_loop_simulation_rate']:.3f}      "
            f"{row['mean_physical_dead_ends']:.1f}"
        )
    print(f"\nResults: {results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
