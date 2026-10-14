#!/usr/bin/env python3
"""Phase-3 oracle-outcome search smoke for the BGB controlled cases.

This module intentionally keeps the first smoke small and auditable.  Search
is over the *physical document graph*.  A source's formal Horn payload is
hidden from every policy and is revealed only by an executed ``read`` action.
Reads made in discarded Beam/PUCT branches are branch-local and still appear
in the cost ledger.

The outcome model in this file is an oracle replay, not an LLM parser.  Its
purpose is to test whether the search/commit/LFP plumbing works before a model
is inserted.  It is not evidence of end-to-end model quality.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EVIDENCE_STATUS = "oracle_outcome_mechanism_smoke"
OUTCOME_MODEL = "deterministic_gold_formal_replay_on_executed_read"
CLAIM_BOUNDARY = (
    "This smoke uses gold formal outcomes after a charged source read. It tests "
    "physical-graph search, branch-local commits, exact LFP and strict state "
    "sharing; it does not test natural-language parsing or establish an "
    "algorithmic advantage."
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(*parts: Any) -> str:
    payload = "|".join(canonical_json(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def stable_unit(*parts: Any) -> float:
    return int(stable_hash(*parts)[:16], 16) / float(16**16)


def _first(raw: Mapping[str, Any], names: Sequence[str], default: Any = None) -> Any:
    for name in names:
        if name in raw and raw[name] is not None:
            return raw[name]
    return default


@dataclass(frozen=True, order=True)
class Atom:
    predicate: str
    arguments: tuple[str, ...] = tuple()

    @property
    def text(self) -> str:
        if not self.arguments:
            return self.predicate
        return f"{self.predicate}({','.join(self.arguments)})"


@dataclass(frozen=True, order=True)
class SourcedFact:
    atom: Atom
    source_id: str


@dataclass(frozen=True, order=True)
class SourcedRule:
    rule_id: str
    head: Atom
    body: tuple[Atom, ...]
    source_id: str


@dataclass(frozen=True)
class FormalOutcome:
    facts: tuple[Atom, ...] = tuple()
    rules: tuple[SourcedRule, ...] = tuple()


@dataclass(frozen=True)
class Source:
    source_id: str
    text: str
    formal_outcome: FormalOutcome


@dataclass(frozen=True)
class SearchCase:
    case_id: str
    public_query: str
    query_atom: Atom
    sources: tuple[Source, ...]
    adjacency: Mapping[str, tuple[str, ...]]
    root_source_id: str
    action_budget: int
    condition: str = "unknown"
    scc_size: int | None = None
    gold_label: str | None = None
    gold_proof_sources: tuple[str, ...] = tuple()
    raw_metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    @property
    def source_map(self) -> dict[str, Source]:
        return {source.source_id: source for source in self.sources}

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(source.source_id for source in self.sources)


def parse_atom(raw: Any) -> Atom:
    if isinstance(raw, Atom):
        return raw
    if isinstance(raw, Mapping):
        if "atom" in raw and "predicate" not in raw:
            return parse_atom(raw["atom"])
        predicate = _first(raw, ("predicate", "pred", "name"))
        arguments = _first(raw, ("arguments", "args", "terms"), [])
        if not isinstance(predicate, str) or not predicate.strip():
            raise ValueError(f"invalid atom: {raw!r}")
        if isinstance(arguments, str):
            arguments = [arguments]
        if not isinstance(arguments, Sequence):
            raise ValueError(f"invalid atom arguments: {raw!r}")
        return Atom(predicate.strip(), tuple(str(item).strip() for item in arguments))
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"invalid atom: {raw!r}")
    value = raw.strip().rstrip(".")
    if value.endswith(")") and "(" in value:
        predicate, tail = value[:-1].split("(", 1)
        return Atom(predicate.strip(), tuple(part.strip() for part in tail.split(",") if part.strip()))
    return Atom(value)


def parse_formal_outcome(raw: Any, source_id: str) -> FormalOutcome:
    """Accept both the V3 one-statement schema and the Phase-1 bundle schema."""

    if raw is None:
        return FormalOutcome()
    facts: list[Atom] = []
    rules: list[SourcedRule] = []

    def add_statement(statement: Any, index: int) -> None:
        if isinstance(statement, str):
            facts.append(parse_atom(statement))
            return
        if not isinstance(statement, Mapping):
            raise ValueError(f"{source_id}: invalid formal statement {statement!r}")
        kind = str(statement.get("kind", "")).lower()
        body_raw = statement.get("body", statement.get("premises", [])) or []
        if isinstance(body_raw, (str, Mapping)):
            body_raw = [body_raw]
        head_raw = _first(statement, ("head", "conclusion", "atom"))
        if head_raw is None and "predicate" in statement:
            head_raw = statement
        head = parse_atom(head_raw)
        body = tuple(sorted((parse_atom(item) for item in body_raw), key=lambda item: item.text))
        if kind == "fact" or (not kind and not body):
            facts.append(head)
            return
        if kind not in ("", "rule", "horn_rule"):
            raise ValueError(f"{source_id}: unsupported formal kind {kind!r}")
        if not body:
            raise ValueError(f"{source_id}: rule without a body")
        rule_id = str(statement.get("rule_id", statement.get("id", f"{source_id}#r{index}")))
        rules.append(SourcedRule(rule_id, head, body, source_id))

    if isinstance(raw, Mapping) and ("facts" in raw or "rules" in raw):
        fact_rows = raw.get("facts", []) or []
        if isinstance(fact_rows, (str, Mapping)):
            fact_rows = [fact_rows]
        for index, fact in enumerate(fact_rows):
            if isinstance(fact, Mapping) and "kind" not in fact:
                fact = {"kind": "fact", "head": fact}
            elif isinstance(fact, str):
                facts.append(parse_atom(fact))
                continue
            add_statement(fact, index)
        rule_rows = raw.get("rules", []) or []
        if isinstance(rule_rows, Mapping):
            rule_rows = [rule_rows]
        for index, rule in enumerate(rule_rows):
            if isinstance(rule, Mapping) and "kind" not in rule:
                rule = dict(rule, kind="rule")
            add_statement(rule, index + len(fact_rows))
    else:
        statements = raw if isinstance(raw, list) else [raw]
        for index, statement in enumerate(statements):
            add_statement(statement, index)

    return FormalOutcome(
        facts=tuple(sorted(set(facts), key=lambda item: item.text)),
        rules=tuple(sorted(set(rules))),
    )


def _normalise_label(value: Any) -> str | None:
    if value is None:
        return None
    label = str(value).strip().lower()
    if label in {"entailed", "true", "yes", "1", "supported"}:
        return "entailed"
    if label in {
        "unknown",
        "pr-unknown",
        "pr_unknown",
        "false",
        "no",
        "0",
        "not_entailed",
        "unsupported",
    }:
        return "unknown"
    return label


def parse_case(raw: Mapping[str, Any]) -> SearchCase:
    # Phase-1's leak-resistant combined file keeps model-visible and evaluator
    # fields in explicit sibling objects.  Normalise it here, while retaining
    # that separation in the on-disk benchmark.
    if isinstance(raw.get("public_case"), Mapping) and isinstance(
        raw.get("evaluator_sidecar"), Mapping
    ):
        public = raw["public_case"]
        evaluator = raw["evaluator_sidecar"]
        fragments = _first(evaluator.get("formal_program", {}), ("fragments",), []) or []
        formal_by_source: dict[str, dict[str, list[Any]]] = defaultdict(
            lambda: {"facts": [], "rules": []}
        )
        for fragment in fragments:
            if not isinstance(fragment, Mapping):
                continue
            source_id = str(fragment.get("source_id"))
            formal_by_source[source_id]["facts"].extend(fragment.get("facts", []) or [])
            formal_by_source[source_id]["rules"].extend(fragment.get("rules", []) or [])
        source_rows = []
        for source in public.get("sources", []):
            source_id = str(_first(source, ("source_id", "id", "node_id")))
            source_rows.append(
                {
                    **source,
                    "source_id": source_id,
                    "text": _first(source, ("rendered_text", "text", "original_text"), ""),
                    "formal_outcome": formal_by_source.get(source_id, {"facts": [], "rules": []}),
                }
            )
        topology = public.get("topology", {})
        adjacency: dict[str, list[str]] = {
            str(source["source_id"]): [] for source in source_rows
        }
        for edge in topology.get("edges", []) if isinstance(topology, Mapping) else []:
            if isinstance(edge, Mapping):
                adjacency.setdefault(str(edge["source"]), []).append(str(edge["target"]))
        anchors = evaluator.get("anchors", {}) if isinstance(evaluator.get("anchors"), Mapping) else {}
        oracle = evaluator.get("oracle", {}) if isinstance(evaluator.get("oracle"), Mapping) else {}
        navigation = (
            evaluator.get("navigation_contract", {})
            if isinstance(evaluator.get("navigation_contract"), Mapping)
            else {}
        )
        query = public.get("query", {}) if isinstance(public.get("query"), Mapping) else {}
        raw = {
            "case_id": public.get("case_id", evaluator.get("case_id")),
            "condition": public.get("condition", evaluator.get("condition")),
            "scc_size": public.get("carrier_size"),
            "public_query": query.get("text", evaluator.get("query_atom")),
            "query_atom": query.get("atom", evaluator.get("query_atom")),
            "sources": source_rows,
            "adjacency": adjacency,
            "root_source_id": public.get(
                "root_source_id",
                navigation.get(
                    "root_source_id",
                    anchors.get(
                        "seed_source_id",
                        (public.get("source_order") or [source_rows[0]["source_id"]])[0],
                    ),
                ),
            ),
            "action_budget": evaluator.get(
                "action_budget",
                navigation.get("default_action_budget", 2 * len(source_rows) + 2),
            ),
            "gold_label": evaluator.get("expected_label", oracle.get("actual_label")),
            "gold": {
                "proof_source_ids": oracle.get("proof_source_ids", []),
            },
            "metadata": {
                "carrier_id": public.get("carrier_id"),
                "topology_sha256": topology.get("sha256") if isinstance(topology, Mapping) else None,
                "navigation_contract": navigation,
                "combined_schema_version": raw.get("schema_version"),
            },
        }
    case_id = str(_first(raw, ("case_id", "id")))
    if not case_id or case_id == "None":
        raise ValueError("case is missing case_id")
    source_rows = _first(raw, ("sources", "windows", "documents"))
    if not isinstance(source_rows, list) or not source_rows:
        raise ValueError(f"{case_id}: sources must be a non-empty list")
    sources: list[Source] = []
    for row in source_rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{case_id}: source is not an object")
        source_id = str(_first(row, ("source_id", "id", "node_id")))
        text = str(
            _first(row, ("text", "rendered_text", "raw_text", "content", "surface"), "")
        )
        formal_raw = _first(
            row,
            ("formal_outcome", "formal", "outcome", "gold_formal", "formal_payload"),
        )
        sources.append(Source(source_id, text, parse_formal_outcome(formal_raw, source_id)))
    if len({source.source_id for source in sources}) != len(sources):
        raise ValueError(f"{case_id}: duplicate source IDs")
    source_ids = {source.source_id for source in sources}

    raw_adjacency = _first(raw, ("adjacency", "source_adjacency", "graph"), {})
    if isinstance(raw_adjacency, Mapping) and "adjacency" in raw_adjacency:
        raw_adjacency = raw_adjacency["adjacency"]
    if not isinstance(raw_adjacency, Mapping):
        raise ValueError(f"{case_id}: adjacency must be an object")
    adjacency: dict[str, tuple[str, ...]] = {}
    for source_id in sorted(source_ids):
        neighbors = raw_adjacency.get(source_id, []) or []
        if isinstance(neighbors, str):
            neighbors = [neighbors]
        clean = tuple(sorted({str(item) for item in neighbors}))
        unknown = set(clean) - source_ids
        if unknown:
            raise ValueError(f"{case_id}: {source_id} has unknown neighbors {sorted(unknown)}")
        adjacency[source_id] = clean

    root = str(_first(raw, ("root_source_id", "root", "start_source_id"), sources[0].source_id))
    if root not in source_ids:
        raise ValueError(f"{case_id}: root {root!r} is not a source")
    query_raw = _first(raw, ("query_atom", "target_atom", "formal_query"))
    if query_raw is None:
        query_block = raw.get("query")
        if isinstance(query_block, Mapping):
            query_raw = _first(query_block, ("atom", "formal", "query_atom"))
    if query_raw is None:
        raise ValueError(f"{case_id}: missing query_atom")
    query_atom = parse_atom(query_raw)
    public_query = str(_first(raw, ("public_query", "query_text", "question"), query_atom.text))

    gold = raw.get("gold", {}) if isinstance(raw.get("gold"), Mapping) else {}
    generator_gold = raw.get("generator_gold", {}) if isinstance(raw.get("generator_gold"), Mapping) else {}
    gold_label = _normalise_label(
        _first(raw, ("gold_label", "label"), _first(gold, ("label",), generator_gold.get("label")))
    )
    proof_sources_raw = _first(
        gold,
        ("proof_source_ids", "proof_sources"),
        _first(generator_gold, ("proof_source_ids", "proof_sources"), []),
    ) or []
    budget = int(_first(raw, ("action_budget", "budget", "max_actions"), max(4, 2 * len(sources))))
    size_raw = _first(raw, ("scc_size", "carrier_size", "size"))
    metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata"), Mapping) else {}
    return SearchCase(
        case_id=case_id,
        public_query=public_query,
        query_atom=query_atom,
        sources=tuple(sources),
        adjacency=adjacency,
        root_source_id=root,
        action_budget=budget,
        condition=str(_first(raw, ("condition", "variant"), metadata.get("condition", "unknown"))),
        scc_size=int(size_raw) if size_raw is not None else len(sources),
        gold_label=gold_label,
        gold_proof_sources=tuple(sorted(str(item) for item in proof_sources_raw)),
        raw_metadata=metadata,
    )


def load_cases(path: Path) -> list[SearchCase]:
    rows: list[Mapping[str, Any]] = []
    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, Mapping):
            candidate = _first(payload, ("cases", "items", "records"), [payload])
            rows = list(candidate)
        else:
            raise ValueError(f"unsupported case file payload: {type(payload).__name__}")
    cases = [parse_case(row) for row in rows]
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("duplicate case IDs")
    return cases


def _minimal_sets(candidates: Iterable[frozenset[str]]) -> frozenset[frozenset[str]]:
    unique = sorted(set(candidates), key=lambda item: (len(item), tuple(sorted(item))))
    kept: list[frozenset[str]] = []
    for candidate in unique:
        if not any(previous <= candidate for previous in kept):
            kept.append(candidate)
    return frozenset(kept)


def exact_lfp(
    facts: Iterable[SourcedFact],
    rules: Iterable[SourcedRule],
) -> tuple[frozenset[Atom], tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]]:
    """Least positive-Horn fixed point plus all inclusion-minimal provenance."""

    proofs: dict[Atom, frozenset[frozenset[str]]] = {}
    for fact in facts:
        proofs[fact.atom] = _minimal_sets((*proofs.get(fact.atom, frozenset()), frozenset({fact.source_id})))
    ordered_rules = tuple(sorted(rules))
    changed = True
    while changed:
        changed = False
        for rule in ordered_rules:
            if not all(atom in proofs for atom in rule.body):
                continue
            combinations: list[frozenset[str]] = [frozenset({rule.source_id})]
            for premise in rule.body:
                combinations = [left | right for left in combinations for right in proofs[premise]]
            updated = _minimal_sets((*proofs.get(rule.head, frozenset()), *combinations))
            if updated != proofs.get(rule.head, frozenset()):
                proofs[rule.head] = updated
                changed = True
    provenance = tuple(
        (
            atom.text,
            tuple(tuple(sorted(proof)) for proof in sorted(proof_sets, key=lambda x: (len(x), tuple(sorted(x))))),
        )
        for atom, proof_sets in sorted(proofs.items(), key=lambda item: item[0].text)
    )
    return frozenset(proofs), provenance


@dataclass(frozen=True)
class SearchState:
    location: str
    sourced_facts: tuple[SourcedFact, ...]
    sourced_rules: tuple[SourcedRule, ...]
    closure: frozenset[Atom]
    provenance: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...]
    coverage: frozenset[str]
    remaining_budget: int

    def proof_sources(self, query: Atom) -> tuple[str, ...]:
        for atom_text, proof_sets in self.provenance:
            if atom_text == query.text and proof_sets:
                return min(proof_sets, key=lambda item: (len(item), item))
        return tuple()


@dataclass(frozen=True, order=True)
class Action:
    kind: str
    target: str

    @property
    def action_id(self) -> str:
        return f"{self.kind}:{self.target}"


@dataclass
class ChargeLedger:
    events: list[dict[str, Any]] = field(default_factory=list)
    real_reads: int = 0
    simulated_reads: int = 0
    real_transitions: int = 0
    simulated_transitions: int = 0

    @property
    def total_reads(self) -> int:
        return self.real_reads + self.simulated_reads

    @property
    def total_transitions(self) -> int:
        return self.real_transitions + self.simulated_transitions

    def record(
        self,
        *,
        phase: str,
        action: Action,
        before: SearchState,
        after: SearchState,
        revealed: FormalOutcome | None,
        branch_id: str,
    ) -> None:
        simulation = phase != "real"
        if simulation:
            self.simulated_transitions += 1
        else:
            self.real_transitions += 1
        if action.kind == "read":
            if simulation:
                self.simulated_reads += 1
            else:
                self.real_reads += 1
        self.events.append(
            {
                "event_index": len(self.events),
                "phase": phase,
                "branch_id": branch_id,
                "action": action.action_id,
                "from": before.location,
                "to": after.location,
                "remaining_budget_before": before.remaining_budget,
                "remaining_budget_after": after.remaining_budget,
                "oracle_reveal": action.kind == "read",
                "revealed_fact_count": len(revealed.facts) if revealed else 0,
                "revealed_rule_count": len(revealed.rules) if revealed else 0,
                "revealed_payload_hash": (
                    stable_hash(
                        [atom.text for atom in revealed.facts],
                        [
                            (
                                rule.rule_id,
                                rule.head.text,
                                [atom.text for atom in rule.body],
                                rule.source_id,
                            )
                            for rule in revealed.rules
                        ],
                    )
                    if revealed
                    else None
                ),
                "coverage_after": sorted(after.coverage),
                "closure_after": sorted(atom.text for atom in after.closure),
            }
        )


class OracleGraphEnvironment:
    """Physical local navigation with a charged oracle replay on ``read``."""

    def __init__(self, case: SearchCase, action_cap: int | None = None):
        self.case = case
        self.source_map = case.source_map
        self.action_cap = min(case.action_budget, action_cap) if action_cap is not None else case.action_budget

    def root(self) -> SearchState:
        return SearchState(
            location=self.case.root_source_id,
            sourced_facts=tuple(),
            sourced_rules=tuple(),
            closure=frozenset(),
            provenance=tuple(),
            coverage=frozenset(),
            remaining_budget=self.action_cap,
        )

    def actions(self, state: SearchState) -> tuple[Action, ...]:
        if state.remaining_budget <= 0 or self.proved(state):
            return tuple()
        actions: list[Action] = []
        if state.location not in state.coverage:
            actions.append(Action("read", state.location))
        actions.extend(Action("move", target) for target in self.case.adjacency.get(state.location, tuple()))
        return tuple(sorted(actions))

    def action_mask(self, state: SearchState) -> tuple[str, ...]:
        return tuple(action.action_id for action in self.actions(state))

    def state_key(self, state: SearchState) -> tuple[Any, ...]:
        program = (
            tuple((fact.atom.text, fact.source_id) for fact in state.sourced_facts),
            tuple(
                (rule.rule_id, rule.head.text, tuple(atom.text for atom in rule.body), rule.source_id)
                for rule in state.sourced_rules
            ),
        )
        return (
            state.location,
            program,
            tuple(sorted(atom.text for atom in state.closure)),
            state.provenance,
            tuple(sorted(state.coverage)),
            self.action_mask(state),
            state.remaining_budget,
        )

    def proved(self, state: SearchState) -> bool:
        return self.case.query_atom in state.closure

    def step(
        self,
        state: SearchState,
        action: Action,
        ledger: ChargeLedger,
        *,
        phase: str,
        branch_id: str,
    ) -> SearchState:
        if action not in self.actions(state):
            raise ValueError(f"illegal action {action.action_id} at {state.location}")
        facts = list(state.sourced_facts)
        rules = list(state.sourced_rules)
        coverage = set(state.coverage)
        location = state.location
        revealed: FormalOutcome | None = None
        if action.kind == "read":
            source = self.source_map[action.target]
            revealed = source.formal_outcome
            facts.extend(SourcedFact(atom, source.source_id) for atom in revealed.facts)
            rules.extend(revealed.rules)
            coverage.add(source.source_id)
        elif action.kind == "move":
            location = action.target
        else:
            raise ValueError(f"unsupported action kind {action.kind!r}")
        sourced_facts = tuple(sorted(set(facts)))
        sourced_rules = tuple(sorted(set(rules)))
        closure, provenance = exact_lfp(sourced_facts, sourced_rules)
        after = SearchState(
            location=location,
            sourced_facts=sourced_facts,
            sourced_rules=sourced_rules,
            closure=closure,
            provenance=provenance,
            coverage=frozenset(coverage),
            remaining_budget=state.remaining_budget - 1,
        )
        ledger.record(
            phase=phase,
            action=action,
            before=state,
            after=after,
            revealed=revealed,
            branch_id=branch_id,
        )
        return after


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _tokens(text: str) -> frozenset[str]:
    return frozenset(token.lower() for token in TOKEN_PATTERN.findall(text))


def public_surface_score(case: SearchCase, source_id: str) -> float:
    """A deliberately cheap score; it never touches ``formal_outcome``."""

    query = _tokens(case.public_query) | _tokens(case.query_atom.text)
    surface = _tokens(case.source_map[source_id].text)
    overlap = len(query & surface) / max(1, len(query))
    return overlap + 0.01 * min(len(surface), 20)


def action_prior(env: OracleGraphEnvironment, state: SearchState, action: Action) -> float:
    if action.kind == "read":
        novelty = 1.0 if action.target not in state.coverage else 0.0
        return 1.2 + novelty + public_surface_score(env.case, action.target)
    novelty = 0.7 if action.target not in state.coverage else 0.0
    return 0.4 + novelty + public_surface_score(env.case, action.target)


def _normalised_priors(
    env: OracleGraphEnvironment, state: SearchState, actions: Sequence[Action]
) -> dict[Action, float]:
    raw = {action: max(1e-6, action_prior(env, state, action)) for action in actions}
    total = sum(raw.values())
    return {action: score / total for action, score in raw.items()}


def state_value(env: OracleGraphEnvironment, state: SearchState) -> float:
    if env.proved(state):
        return 1.0
    closure_mass = len(state.closure) / max(1, len(state.closure) + len(state.sourced_rules) + 3)
    coverage = len(state.coverage) / max(1, len(env.case.sources))
    return min(0.49, 0.20 * closure_mass + 0.10 * coverage)


def _result(
    *,
    method: str,
    env: OracleGraphEnvironment,
    state: SearchState,
    ledger: ChargeLedger,
    seed: int,
    nodes: int = 0,
    distinct_state_keys: int = 0,
    tt_hits: int = 0,
    simulations: int = 0,
    simulation_cap: int = 0,
    real_actions: Sequence[str] = tuple(),
) -> dict[str, Any]:
    proof = env.proved(state)
    predicted = "entailed" if proof else "unknown"
    return {
        "evidence_status": EVIDENCE_STATUS,
        "outcome_model": OUTCOME_MODEL,
        "claim_boundary": CLAIM_BOUNDARY,
        "case_id": env.case.case_id,
        "condition": env.case.condition,
        "scc_size": env.case.scc_size,
        "method": method,
        "seed": seed,
        "caps": {
            "real_action_cap": env.action_cap,
            "simulation_transition_cap": simulation_cap,
        },
        "proof_recovered": proof,
        "predicted_label": predicted,
        "gold_label": env.case.gold_label,
        "label_correct": predicted == env.case.gold_label if env.case.gold_label else None,
        "proof_sources": list(state.proof_sources(env.case.query_atom)),
        "gold_proof_sources": list(env.case.gold_proof_sources),
        "proof_source_match": (
            set(state.proof_sources(env.case.query_atom)) == set(env.case.gold_proof_sources)
            if proof and env.case.gold_proof_sources
            else None
        ),
        "real_actions": list(real_actions),
        "final_coverage": sorted(state.coverage),
        "final_closure": sorted(atom.text for atom in state.closure),
        "metrics": {
            "real_reads": ledger.real_reads,
            "simulated_reads": ledger.simulated_reads,
            "total_charged_reads": ledger.total_reads,
            "real_transitions": ledger.real_transitions,
            "simulated_transitions": ledger.simulated_transitions,
            "total_charged_transitions": ledger.total_transitions,
            "nodes": nodes,
            "distinct_state_keys": distinct_state_keys,
            "tt_hits": tt_hits,
            "simulations": simulations,
        },
        "ledger": ledger.events,
    }


def _path_to_nearest_unread(env: OracleGraphEnvironment, state: SearchState) -> list[str]:
    queue: deque[tuple[str, list[str]]] = deque([(state.location, [])])
    seen = {state.location}
    while queue:
        node, path = queue.popleft()
        if node not in state.coverage and node != state.location:
            return path
        for target in env.case.adjacency.get(node, tuple()):
            if target not in seen:
                seen.add(target)
                queue.append((target, [*path, target]))
    return []


def run_direct_proxy(case: SearchCase, seed: int, action_cap: int | None = None) -> dict[str, Any]:
    """Fixed topology scan followed by one final answer (no closure-guided policy)."""

    env = OracleGraphEnvironment(case, action_cap)
    state = env.root()
    ledger = ChargeLedger()
    actions_taken: list[str] = []
    while state.remaining_budget > 0 and not env.proved(state):
        if state.location not in state.coverage:
            action = Action("read", state.location)
        else:
            path = _path_to_nearest_unread(env, state)
            if not path:
                break
            action = Action("move", path[0])
        state = env.step(state, action, ledger, phase="real", branch_id="direct")
        actions_taken.append(action.action_id)
    return _result(
        method="Direct/global-one-shot proxy",
        env=env,
        state=state,
        ledger=ledger,
        seed=seed,
        real_actions=actions_taken,
    )


def _greedy_action(
    env: OracleGraphEnvironment,
    state: SearchState,
    visit_counts: Mapping[str, int],
    seed: int,
) -> Action | None:
    actions = env.actions(state)
    if not actions:
        return None

    def score(action: Action) -> tuple[float, float, str]:
        prior = action_prior(env, state, action)
        if action.kind == "move":
            prior -= 0.35 * visit_counts.get(action.target, 0)
        jitter = stable_unit(seed, env.case.case_id, state.remaining_budget, action.action_id) * 1e-9
        return prior + jitter, -len(action.action_id), action.action_id

    return max(actions, key=score)


def run_greedy(case: SearchCase, seed: int, action_cap: int | None = None) -> dict[str, Any]:
    env = OracleGraphEnvironment(case, action_cap)
    state = env.root()
    ledger = ChargeLedger()
    actions_taken: list[str] = []
    visits: dict[str, int] = defaultdict(int)
    visits[state.location] += 1
    while state.remaining_budget > 0 and not env.proved(state):
        action = _greedy_action(env, state, visits, seed)
        if action is None:
            break
        state = env.step(state, action, ledger, phase="real", branch_id="greedy")
        actions_taken.append(action.action_id)
        visits[state.location] += 1
    return _result(
        method="Surface Greedy",
        env=env,
        state=state,
        ledger=ledger,
        seed=seed,
        real_actions=actions_taken,
    )


@dataclass(frozen=True)
class BeamItem:
    state: SearchState
    first_action: Action
    path: tuple[str, ...]
    score: float


def _beam_first_action(
    env: OracleGraphEnvironment,
    root: SearchState,
    ledger: ChargeLedger,
    *,
    seed: int,
    beam_width: int,
    depth: int,
    transition_allowance: int,
    round_index: int,
) -> tuple[Action | None, int, int]:
    frontier: list[tuple[SearchState, Action | None, tuple[str, ...]]] = [(root, None, tuple())]
    expanded = 0
    state_keys: set[tuple[Any, ...]] = {env.state_key(root)}
    leaves: list[BeamItem] = []
    for level in range(depth):
        next_items: list[BeamItem] = []
        for item_index, (state, first, path) in enumerate(frontier):
            for action in env.actions(state):
                if expanded >= transition_allowance:
                    break
                branch_id = f"beam-r{round_index}-d{level}-i{item_index}-{action.action_id}"
                child = env.step(state, action, ledger, phase="beam", branch_id=branch_id)
                expanded += 1
                state_keys.add(env.state_key(child))
                first_action = first or action
                child_path = (*path, action.action_id)
                score = state_value(env, child) + 0.02 * len(child.coverage)
                score += stable_unit(seed, env.case.case_id, round_index, child_path) * 1e-9
                candidate = BeamItem(child, first_action, child_path, score)
                next_items.append(candidate)
                leaves.append(candidate)
            if expanded >= transition_allowance:
                break
        if not next_items:
            break
        next_items.sort(key=lambda item: (item.score, tuple(reversed(item.path))), reverse=True)
        kept = next_items[:beam_width]
        frontier = [(item.state, item.first_action, item.path) for item in kept]
        if any(env.proved(item.state) for item in kept):
            break
    if not leaves:
        return None, expanded, len(state_keys)
    best = max(leaves, key=lambda item: (env.proved(item.state), item.score, tuple(reversed(item.path))))
    return best.first_action, expanded, len(state_keys)


def run_beam(
    case: SearchCase,
    seed: int,
    action_cap: int | None = None,
    *,
    simulation_cap: int = 256,
    beam_width: int = 4,
    beam_depth: int = 4,
) -> dict[str, Any]:
    env = OracleGraphEnvironment(case, action_cap)
    state = env.root()
    ledger = ChargeLedger()
    actions_taken: list[str] = []
    expanded_total = 0
    distinct_total = 0
    round_index = 0
    while state.remaining_budget > 0 and not env.proved(state):
        allowance = simulation_cap - expanded_total
        if allowance <= 0:
            visits = defaultdict(int)
            action = _greedy_action(env, state, visits, seed + round_index)
        else:
            action, expanded, distinct = _beam_first_action(
                env,
                state,
                ledger,
                seed=seed,
                beam_width=beam_width,
                depth=beam_depth,
                transition_allowance=allowance,
                round_index=round_index,
            )
            expanded_total += expanded
            distinct_total += distinct
        if action is None:
            break
        state = env.step(state, action, ledger, phase="real", branch_id=f"beam-root-{round_index}")
        actions_taken.append(action.action_id)
        round_index += 1
    return _result(
        method="Beam",
        env=env,
        state=state,
        ledger=ledger,
        seed=seed,
        nodes=expanded_total + 1,
        distinct_state_keys=distinct_total,
        simulations=round_index,
        simulation_cap=simulation_cap,
        real_actions=actions_taken,
    )


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
    state: SearchState
    visits: int = 0
    value_sum: float = 0.0
    edges: dict[Action, EdgeStats] = field(default_factory=dict)


class PUCTPlanner:
    """Finite-horizon PUCT; strict TT sharing is the only Tree/Graph switch."""

    def __init__(
        self,
        env: OracleGraphEnvironment,
        root_state: SearchState,
        ledger: ChargeLedger,
        *,
        seed: int,
        merge_states: bool,
        c_puct: float = 1.35,
    ):
        self.env = env
        self.ledger = ledger
        self.rng = random.Random(seed)
        self.seed = seed
        self.merge_states = merge_states
        self.c_puct = c_puct
        self.nodes: dict[int, PUCTNode] = {}
        self.tt: dict[tuple[Any, ...], int] = {}
        self.tt_hits = 0
        self.transition_count = 0
        self.simulations = 0
        self.root_id, _ = self.intern_state(root_state)

    def intern_state(self, state: SearchState) -> tuple[int, bool]:
        key = self.env.state_key(state)
        if self.merge_states and key in self.tt:
            self.tt_hits += 1
            return self.tt[key], True
        node_id = len(self.nodes)
        actions = self.env.actions(state)
        priors = _normalised_priors(self.env, state, actions) if actions else {}
        node = PUCTNode(
            node_id=node_id,
            state=state,
            edges={action: EdgeStats(prior) for action, prior in priors.items()},
        )
        self.nodes[node_id] = node
        if self.merge_states:
            self.tt[key] = node_id
        return node_id, False

    def _select(self, node: PUCTNode) -> Action:
        unvisited = [action for action, edge in node.edges.items() if edge.visits == 0]
        if unvisited:
            # Common deterministic expansion order keeps Tree and Graph paired.
            return max(unvisited, key=lambda action: (node.edges[action].prior, action.action_id))
        root = math.sqrt(max(1, node.visits))
        return max(
            node.edges,
            key=lambda action: (
                node.edges[action].q
                + self.c_puct * node.edges[action].prior * root / (1 + node.edges[action].visits),
                node.edges[action].prior,
                action.action_id,
            ),
        )

    def simulate_once(self, transition_allowance: int) -> int:
        if transition_allowance <= 0:
            return 0
        self.simulations += 1
        simulation_id = self.simulations
        node_id = self.root_id
        path: list[tuple[int, Action]] = []
        consumed = 0
        visited_ids: set[int] = set()
        while consumed < transition_allowance:
            node = self.nodes[node_id]
            if self.env.proved(node.state) or not node.edges:
                break
            if node_id in visited_ids:
                # Remaining budget normally prevents a literal cycle; this is a safety guard.
                break
            visited_ids.add(node_id)
            action = self._select(node)
            edge = node.edges[action]
            child_state = self.env.step(
                node.state,
                action,
                self.ledger,
                phase="simulation",
                branch_id=f"puct-s{simulation_id}",
            )
            consumed += 1
            if edge.child_id is None:
                child_id, _ = self.intern_state(child_state)
                edge.child_id = child_id
                path.append((node_id, action))
                node_id = child_id
                # One public-prior rollout after expansion; all transitions are charged.
                while consumed < transition_allowance:
                    rollout_node = self.nodes[node_id]
                    if self.env.proved(rollout_node.state) or not rollout_node.edges:
                        break
                    rollout_action = max(
                        rollout_node.edges,
                        key=lambda item: (
                            rollout_node.edges[item].prior
                            + stable_unit(self.seed, simulation_id, consumed, item.action_id) * 1e-8,
                            item.action_id,
                        ),
                    )
                    rollout_edge = rollout_node.edges[rollout_action]
                    rollout_state = self.env.step(
                        rollout_node.state,
                        rollout_action,
                        self.ledger,
                        phase="simulation",
                        branch_id=f"puct-s{simulation_id}-rollout",
                    )
                    consumed += 1
                    if rollout_edge.child_id is None:
                        rollout_child, _ = self.intern_state(rollout_state)
                        rollout_edge.child_id = rollout_child
                    else:
                        rollout_child = rollout_edge.child_id
                    path.append((node_id, rollout_action))
                    node_id = rollout_child
                break
            path.append((node_id, action))
            expected_key = self.env.state_key(self.nodes[edge.child_id].state)
            if self.env.state_key(child_state) != expected_key:
                raise AssertionError("deterministic edge changed child state")
            node_id = edge.child_id
        leaf = self.nodes[node_id]
        value = state_value(self.env, leaf.state)
        leaf.visits += 1
        leaf.value_sum += value
        for parent_id, action in reversed(path):
            parent = self.nodes[parent_id]
            edge = parent.edges[action]
            edge.visits += 1
            edge.value_sum += value
            parent.visits += 1
            parent.value_sum += value
        self.transition_count += consumed
        return consumed

    def run(self, transition_cap: int, simulation_cap: int | None = None) -> Action | None:
        max_simulations = simulation_cap if simulation_cap is not None else transition_cap
        while self.transition_count < transition_cap and self.simulations < max_simulations:
            consumed = self.simulate_once(transition_cap - self.transition_count)
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

    @property
    def distinct_state_keys(self) -> int:
        return len({self.env.state_key(node.state) for node in self.nodes.values()})


def run_puct(
    case: SearchCase,
    seed: int,
    action_cap: int | None = None,
    *,
    simulation_transition_cap: int = 512,
    simulations_per_move: int = 32,
    merge_states: bool,
    method_name: str | None = None,
) -> dict[str, Any]:
    env = OracleGraphEnvironment(case, action_cap)
    state = env.root()
    ledger = ChargeLedger()
    actions_taken: list[str] = []
    total_nodes = 0
    distinct_keys: set[tuple[Any, ...]] = set()
    total_tt_hits = 0
    total_simulations = 0
    used_simulation_transitions = 0
    decision = 0
    while state.remaining_budget > 0 and not env.proved(state):
        allowance = min(
            simulation_transition_cap - used_simulation_transitions,
            max(1, simulations_per_move * max(1, state.remaining_budget)),
        )
        if allowance <= 0:
            action = _greedy_action(env, state, defaultdict(int), seed + decision)
        else:
            planner = PUCTPlanner(
                env,
                state,
                ledger,
                seed=seed + 1009 * decision,
                merge_states=merge_states,
            )
            action = planner.run(allowance, simulation_cap=simulations_per_move)
            used_simulation_transitions += planner.transition_count
            total_nodes += len(planner.nodes)
            distinct_keys.update(env.state_key(node.state) for node in planner.nodes.values())
            total_tt_hits += planner.tt_hits
            total_simulations += planner.simulations
        if action is None:
            break
        state = env.step(state, action, ledger, phase="real", branch_id=f"puct-root-{decision}")
        actions_taken.append(action.action_id)
        decision += 1
    name = method_name or ("GraphPUCT (exact merge)" if merge_states else "TreePUCT (no merge)")
    return _result(
        method=name,
        env=env,
        state=state,
        ledger=ledger,
        seed=seed,
        nodes=total_nodes,
        distinct_state_keys=len(distinct_keys),
        tt_hits=total_tt_hits,
        simulations=total_simulations,
        simulation_cap=simulation_transition_cap,
        real_actions=actions_taken,
    )


def run_method(
    case: SearchCase,
    method: str,
    seed: int,
    *,
    action_cap: int | None = None,
    simulation_transition_cap: int = 512,
    simulations_per_move: int = 32,
    beam_width: int = 4,
    beam_depth: int = 4,
    merge_override: bool | None = None,
) -> dict[str, Any]:
    key = method.strip().lower()
    if key in {"direct", "direct/global-one-shot proxy", "global"}:
        return run_direct_proxy(case, seed, action_cap)
    if key in {"greedy", "surface greedy"}:
        return run_greedy(case, seed, action_cap)
    if key == "beam":
        return run_beam(
            case,
            seed,
            action_cap,
            simulation_cap=simulation_transition_cap,
            beam_width=beam_width,
            beam_depth=beam_depth,
        )
    if key in {"tree", "treepuct", "treemcts"}:
        merge = False if merge_override is None else merge_override
        return run_puct(
            case,
            seed,
            action_cap,
            simulation_transition_cap=simulation_transition_cap,
            simulations_per_move=simulations_per_move,
            merge_states=merge,
            method_name="TreePUCT (no merge)" if not merge else "TreePUCT (merge override)",
        )
    if key in {"graph", "graphpuct", "mcgs"}:
        merge = True if merge_override is None else merge_override
        return run_puct(
            case,
            seed,
            action_cap,
            simulation_transition_cap=simulation_transition_cap,
            simulations_per_move=simulations_per_move,
            merge_states=merge,
            method_name="GraphPUCT (exact merge)" if merge else "GraphPUCT (merge disabled)",
        )
    raise ValueError(f"unknown method {method!r}")
