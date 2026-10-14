#!/usr/bin/env python3
"""Run the deterministic Experiment V1 gold-replay smoke test.

This is deliberately *not* an implementation of LFP-MCGS.  It asks three
earlier questions with exact dataset semantics:

1. Is there enough source-acquisition pressure for scheduling to matter?
2. Does a deployable, surface-only frontier updated by exact closure provide a
   useful signal over static ordering and random acquisition?
3. Do order-equivalent acquisition histories create enough safe
   transpositions to justify testing MCGS later?

Unseen source semantics are never used by the deployable policies.  Gold proof
covers are used only for sampling, normalized budgets, and an explicitly
labelled lower-bound row.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import importlib.util
import itertools
import json
import math
import platform
import random
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


SCRIPT_PATH = Path(__file__).resolve()
NAACL_ROOT = SCRIPT_PATH.parents[2]
AUDIT_ROOT = NAACL_ROOT / "dataset_audit"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pw = load_module("experiment_v1_pw_audit", AUDIT_ROOT / "audit_productive_recursion.py")
step = load_module("experiment_v1_step_audit", AUDIT_ROOT / "audit_stepgame.py")
clutrr = load_module("experiment_v1_clutrr_audit", AUDIT_ROOT / "audit_clutrr.py")


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "does",
    "if",
    "in",
    "is",
    "it",
    "of",
    "or",
    "something",
    "someone",
    "that",
    "the",
    "then",
    "to",
    "what",
    "when",
    "with",
}


def stable_key(seed: str, *parts: object) -> str:
    payload = "|".join([seed, *(str(part) for part in parts)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def surface_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in STOPWORDS and len(token) > 1
    }


def atom_tokens(atom: Any) -> set[str]:
    predicate = atom.predicate.rsplit("::", 1)[0]
    tokens = surface_tokens(predicate.replace("_", " "))
    for argument in atom.arguments:
        tokens.update(surface_tokens(argument.replace("_", " ")))
    return tokens


def lexical_score(tokens: set[str], wanted: set[str], idf: dict[str, float]) -> float:
    return sum(idf.get(token, 1.0) for token in tokens & wanted)


def idf_for_sources(source_tokens: dict[str, set[str]]) -> dict[str, float]:
    counts = Counter(token for tokens in source_tokens.values() for token in tokens)
    total = len(source_tokens)
    return {
        token: math.log((total + 1) / (count + 1)) + 1
        for token, count in counts.items()
    }


@dataclass(frozen=True)
class Evaluation:
    success: bool
    closure_size: int
    progress_size: int
    closure_signature: tuple[str, ...]
    payload: Any = None


@dataclass
class ReplayCase:
    dataset: str
    case_id: str
    source_ids: tuple[str, ...]
    minimum_cover: int
    gold_cover: tuple[str, ...]
    metadata: dict[str, Any]
    evaluate_uncached: Callable[[frozenset[str]], Evaluation]
    static_score: Callable[[str], float]
    dynamic_score: Callable[[frozenset[str], str, Evaluation], float]
    _cache: dict[frozenset[str], Evaluation] = field(default_factory=dict)

    def evaluate(self, selected: Iterable[str]) -> Evaluation:
        key = frozenset(selected)
        if key not in self._cache:
            self._cache[key] = self.evaluate_uncached(key)
        return self._cache[key]


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def source_groups(theory: dict) -> tuple[tuple[str, ...], dict[str, list[tuple[str, dict]]]]:
    mappings = theory.get("mappings") or {}
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    order: list[str] = []
    for kind, records in (("fact", theory["triples"]), ("rule", theory["rules"])):
        for record_id, record in records.items():
            source_id = mappings.get(record_id, record_id)
            if source_id not in groups:
                order.append(source_id)
            groups[source_id].append((kind, {"record_id": record_id, **record}))
    return tuple(order), groups


def build_proofwriter_case(theory: dict, question_id: str, audit_row: dict) -> ReplayCase:
    source_ids, groups = source_groups(theory)
    question = theory["questions"][question_id]
    query_atom = pw.parse_fact(question["representation"])
    opposite_atom = pw.complement(query_atom)

    facts_by_source: dict[str, list[Any]] = defaultdict(list)
    schemas_by_source: dict[str, list[Any]] = defaultdict(list)
    visible_text: dict[str, str] = {}
    for source_id, records in groups.items():
        visible_text[source_id] = " ".join(record["text"] for _kind, record in records)
        for kind, record in records:
            if kind == "fact":
                facts_by_source[source_id].append(pw.parse_fact(record["representation"]))
            else:
                schemas_by_source[source_id].append(
                    pw.parse_rule(record["record_id"], record["representation"])
                )

    all_facts = [fact for facts in facts_by_source.values() for fact in facts]
    all_schemas = [rule for rules in schemas_by_source.values() for rule in rules]
    constants = sorted(
        {
            argument
            for atom in all_facts
            for argument in atom.arguments
            if argument not in pw.VARIABLES
        }
        | {
            argument
            for rule in all_schemas
            for atom in (*rule.body, rule.head)
            for argument in atom.arguments
            if argument not in pw.VARIABLES
        }
    )
    grounded_by_source = {
        source_id: pw.ground_rules(rules, constants)
        for source_id, rules in schemas_by_source.items()
    }
    source_token_map = {
        source_id: surface_tokens(text) for source_id, text in visible_text.items()
    }
    idf = idf_for_sources(source_token_map)
    query_tokens = (
        surface_tokens(question["question"])
        | atom_tokens(query_atom)
        | atom_tokens(opposite_atom)
    )
    source_position = {source_id: index for index, source_id in enumerate(source_ids)}

    proof_covers = pw.source_ids_for_proof(question, theory.get("mappings"))
    proof_covers = [cover for cover in proof_covers if cover <= set(source_ids)]
    if not proof_covers:
        raise ValueError(f"No source-linked proof: {theory['id']}::{question_id}")
    gold_cover = tuple(
        sorted(min(proof_covers, key=lambda cover: (len(cover), sorted(cover))))
    )
    if len(gold_cover) != audit_row["minimum_source_cover"]:
        raise AssertionError("Proof cover disagrees with audited minimum")

    def evaluate(selected: frozenset[str]) -> Evaluation:
        facts = {
            fact
            for source_id in selected
            for fact in facts_by_source.get(source_id, ())
        }
        rules = [
            rule
            for source_id in selected
            for rule in grounded_by_source.get(source_id, ())
        ]
        closure, _ranks, _productive, _cross = pw.saturate(facts, rules)
        signature = tuple(
            sorted(
                f"{atom.predicate}({','.join(atom.arguments)})"
                for atom in closure
            )
        )
        return Evaluation(
            # Gold answer is used only here, never to choose the frontier.
            success=pw.predicted_answer(question, closure) == question["answer"],
            closure_size=len(closure),
            progress_size=max(0, len(closure - facts)),
            closure_signature=signature,
            payload=(closure, rules),
        )

    def static_score(source_id: str) -> float:
        return lexical_score(source_token_map[source_id], query_tokens, idf)

    def dynamic_score(
        selected: frozenset[str], source_id: str, current: Evaluation
    ) -> float:
        closure, acquired_rules = current.payload
        frontier: set[Any] = set()
        # The policy does not know the label.  It tracks both the stated query
        # and its explicit complement until either becomes provable.
        pending = [query_atom, opposite_atom]
        visited: set[Any] = set()
        while pending:
            atom = pending.pop()
            if atom in closure or atom in visited:
                continue
            visited.add(atom)
            producers = [rule for rule in acquired_rules if rule.head == atom]
            if not producers:
                frontier.add(atom)
                continue
            for rule in producers:
                missing = [premise for premise in rule.body if premise not in closure]
                if missing:
                    pending.extend(missing)
                else:
                    frontier.add(atom)
        wanted = set().union(*(atom_tokens(atom) for atom in frontier)) if frontier else query_tokens
        dynamic = lexical_score(source_token_map[source_id], wanted, idf)
        static = lexical_score(source_token_map[source_id], query_tokens, idf)
        # Position only resolves exact ties and never changes the semantic score.
        return 4.0 * dynamic + 0.25 * static - source_position[source_id] * 1e-8

    return ReplayCase(
        dataset="ProofWriter D5",
        case_id=f"{theory['id']}::{question_id}",
        source_ids=source_ids,
        minimum_cover=audit_row["minimum_source_cover"],
        gold_cover=gold_cover,
        metadata={
            "theory_id": theory["id"],
            "question_id": question_id,
            "query_rank": audit_row["query_rank"],
            "cross_constant": audit_row["cross_constant"],
            "candidate_sources": len(source_ids),
            "longest_internal_derivation_chain": audit_row[
                "longest_internal_derivation_chain"
            ],
        },
        evaluate_uncached=evaluate,
        static_score=static_score,
        dynamic_score=dynamic_score,
    )


def select_proofwriter_cases(config: dict, input_path: Path) -> list[ReplayCase]:
    if config["selection"]["max_queries_per_theory"] != 1:
        raise ValueError("V1 implements exactly one selected query per theory")
    audited = pw.audit([str(input_path)], allow_explicit_negation=False)
    theories = {row["id"]: row for row in read_jsonl(input_path)}
    selection = config["selection"]
    candidates = []
    for row in audited["causal_query_index"]:
        cover = row["minimum_source_cover"]
        if cover is None or cover < selection["minimum_source_cover_min"]:
            continue
        if row["query_rank"] not in selection["query_ranks"]:
            continue
        if row["longest_internal_derivation_chain"] < selection[
            "longest_internal_chain_min"
        ]:
            continue
        if row["candidate_sources"] / cover < selection[
            "candidate_to_cover_ratio_min"
        ]:
            continue
        candidates.append(row)

    by_stratum: dict[tuple[bool, int], list[dict]] = defaultdict(list)
    for row in candidates:
        by_stratum[(bool(row["cross_constant"]), int(row["query_rank"]))].append(row)

    selected_rows = []
    used_theories: set[str] = set()
    seed = config_root["selection_seed"]
    for cross_constant in selection["cross_constant"]:
        for rank in selection["query_ranks"]:
            rows = sorted(
                by_stratum[(cross_constant, rank)],
                key=lambda row: stable_key(
                    seed, "proofwriter", row["theory_id"], row["question_id"]
                ),
            )
            chosen = []
            for row in rows:
                if row["theory_id"] in used_theories:
                    continue
                chosen.append(row)
                used_theories.add(row["theory_id"])
                if len(chosen) == selection["per_stratum"]:
                    break
            if len(chosen) != selection["per_stratum"]:
                raise AssertionError(
                    f"Insufficient ProofWriter cases for stratum {(cross_constant, rank)}"
                )
            selected_rows.extend(chosen)

    cases = [
        build_proofwriter_case(
            theories[row["theory_id"]], row["question_id"], row
        )
        for row in selected_rows
    ]
    if len(cases) != config["sample_size"]:
        raise AssertionError("ProofWriter sample size mismatch")
    return cases


def stepgame_components(constraints: Sequence[tuple]) -> list[set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for a, b, _dx, _dy in constraints:
        adjacency[a].add(b)
        adjacency[b].add(a)
    components: list[set[str]] = []
    seen: set[str] = set()
    for node in adjacency:
        if node in seen:
            continue
        component = {node}
        stack = [node]
        seen.add(node)
        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components


def build_stepgame_case(index: int, example: dict, parser: Any) -> ReplayCase:
    question = step.parse_question(example["question"])
    if question is None:
        raise ValueError(f"Unparseable StepGame question at {index}")
    query_source, query_target = question
    parses = [parser.parse(sentence) for sentence in example["story"]]
    if not all(item.status == "canonical" for item in parses):
        raise ValueError("Noncanonical StepGame case reached builder")
    constraints = [item.constraints[0] for item in parses]
    # This is the free surface/entity index, not a peek at the hidden relation
    # vector.  StepGame entities are single capital letters in the raw text.
    raw_endpoints = [
        frozenset(re.findall(r"\b[A-Z]\b", sentence))
        for sentence in example["story"]
    ]
    if any(len(endpoints) not in {1, 2} for endpoints in raw_endpoints):
        raise ValueError("Unexpected StepGame surface entity inventory")
    metrics = step.canonical_story_metrics(
        constraints, query_source, query_target, example["label"]
    )
    distance, proof_indices = step.shortest_path_with_edges(
        constraints, query_source, query_target
    )
    if distance is None:
        raise ValueError("Selected StepGame case has no proof")
    source_ids = tuple(f"sentence-{item + 1}" for item in range(len(constraints)))
    constraint_by_source = dict(zip(source_ids, constraints))
    endpoints_by_source = dict(zip(source_ids, raw_endpoints))
    source_position = {source_id: position for position, source_id in enumerate(source_ids)}

    def evaluate(selected: frozenset[str]) -> Evaluation:
        acquired = [constraint_by_source[source_id] for source_id in selected]
        label, consistent = step.query_label(acquired, query_source, query_target)
        components = stepgame_components(acquired)
        closure_size = sum(len(component) * (len(component) - 1) for component in components)
        progress_size = max(0, closure_size - 2 * len(set(acquired)))
        coordinates, component_map, _ = step.solve_constraints(acquired)
        # Canonicalize by pairwise offsets, not arbitrary component roots/IDs.
        # The same acquired fact set must have the same signature regardless
        # of set iteration order.
        signature = tuple(
            sorted(
                f"{left}>{right}:{coordinates[left][0] - coordinates[right][0]},"
                f"{coordinates[left][1] - coordinates[right][1]}"
                for left in coordinates
                for right in coordinates
                if left != right and component_map[left] == component_map[right]
            )
        )
        return Evaluation(
            success=consistent and label == example["label"],
            closure_size=closure_size,
            progress_size=progress_size,
            closure_signature=signature,
            payload=(acquired, components),
        )

    query_entities = {query_source, query_target}

    def static_score(source_id: str) -> float:
        return float(len(endpoints_by_source[source_id] & query_entities)) - source_position[
            source_id
        ] * 1e-8

    def dynamic_score(
        selected: frozenset[str], source_id: str, current: Evaluation
    ) -> float:
        _acquired, components = current.payload
        source_component = next(
            (component for component in components if query_source in component),
            {query_source},
        )
        target_component = next(
            (component for component in components if query_target in component),
            {query_target},
        )
        endpoints = endpoints_by_source[source_id]
        bridges = bool(endpoints & source_component) and bool(endpoints & target_component)
        touches_source = bool(endpoints & source_component)
        touches_target = bool(endpoints & target_component)
        expands = bool(endpoints & (source_component | target_component))
        return (
            100.0 * bridges
            + 12.0 * (touches_source + touches_target)
            + 3.0 * expands
            + float(len(endpoints & query_entities))
            - source_position[source_id] * 1e-8
        )

    gold_cover = tuple(source_ids[item] for item in proof_indices)
    return ReplayCase(
        dataset="StepGame",
        case_id=f"stepgame-test-line-{index + 1}",
        source_ids=source_ids,
        minimum_cover=distance,
        gold_cover=gold_cover,
        metadata={
            "line_index": index,
            "k_hop": int(example["k_hop"]),
            "candidate_sources": len(source_ids),
            "minimum_support_sources": distance,
            "candidate_to_support_ratio": metrics[
                "candidate_to_minimum_support_ratio"
            ],
        },
        evaluate_uncached=evaluate,
        static_score=static_score,
        dynamic_score=dynamic_score,
    )


def select_stepgame_cases(config: dict, test_path: Path, template_path: Path) -> list[ReplayCase]:
    parser = step.OfficialTemplateParser(template_path)
    selection = config["selection"]
    if not selection["require_fully_canonical"]:
        raise ValueError("V1 only implements the fully-canonical StepGame slice")
    pools: dict[int, list[tuple[int, dict]]] = defaultdict(list)
    with test_path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            example = json.loads(line)
            hop = int(example["k_hop"])
            if hop not in selection["k_hops"]:
                continue
            question = step.parse_question(example["question"])
            if question is None:
                continue
            parses = [parser.parse(sentence) for sentence in example["story"]]
            if not all(item.status == "canonical" for item in parses):
                continue
            constraints = [item.constraints[0] for item in parses]
            metrics = step.canonical_story_metrics(
                constraints, question[0], question[1], example["label"]
            )
            if metrics["minimum_support_sources"] < selection["minimum_support_min"]:
                continue
            if metrics["candidate_to_minimum_support_ratio"] < selection[
                "candidate_to_support_ratio_min"
            ]:
                continue
            pools[hop].append((index, example))

    cases: list[ReplayCase] = []
    for hop in selection["k_hops"]:
        chosen = sorted(
            pools[hop],
            key=lambda item: stable_key(
                config_root["selection_seed"], "stepgame", item[0]
            ),
        )[: selection["per_hop"]]
        if len(chosen) != selection["per_hop"]:
            raise AssertionError(f"Insufficient StepGame k={hop} cases")
        cases.extend(build_stepgame_case(index, example, parser) for index, example in chosen)
    if len(cases) != config["sample_size"]:
        raise AssertionError("StepGame sample size mismatch")
    return cases


def budget_steps(case: ReplayCase) -> dict[str, int]:
    return {
        "MAC": min(len(case.source_ids), case.minimum_cover),
        "2xMAC": min(len(case.source_ids), 2 * case.minimum_cover),
        "3xMAC_cap_N": min(len(case.source_ids), 3 * case.minimum_cover),
    }


def run_sequence(case: ReplayCase, sequence: Sequence[str]) -> dict:
    selected: set[str] = set()
    previous = case.evaluate(selected)
    first_proof = None
    productive_reveals = 0
    total_progress_delta = 0
    success_by_step = {0: previous.success}
    for step_id, source_id in enumerate(sequence, start=1):
        selected.add(source_id)
        current = case.evaluate(selected)
        # Dataset-specific closure item counts are monotone; they are reported
        # only within a dataset and never compared across semantic profiles.
        progress_delta = max(0, current.closure_size - previous.closure_size)
        if first_proof is None:
            productive_reveals += int(progress_delta > 0)
            total_progress_delta += progress_delta
        if current.success and first_proof is None:
            first_proof = step_id
        success_by_step[step_id] = current.success
        previous = current
    if first_proof is None:
        raise AssertionError(f"Full source set failed for {case.case_id}")
    budgets = budget_steps(case)
    return {
        "first_proof": first_proof,
        "first_proof_over_MAC": first_proof / case.minimum_cover,
        "success_at": {
            label: bool(success_by_step.get(step, False))
            for label, step in budgets.items()
        },
        "productive_reveal_rate_until_proof": productive_reveals / first_proof,
        "all_closure_items_per_reveal_until_proof": total_progress_delta / first_proof,
    }


def policy_sequence(case: ReplayCase, policy: str, random_seed: int | None = None) -> list[str]:
    if policy == "source_order":
        return list(case.source_ids)
    if policy == "random":
        rng = random.Random(f"{random_seed}|{case.case_id}")
        sequence = list(case.source_ids)
        rng.shuffle(sequence)
        return sequence
    if policy == "static_surface":
        return sorted(case.source_ids, key=lambda source_id: -case.static_score(source_id))
    if policy == "gold_minimum_proof_lower_bound":
        selected = set(case.gold_cover)
        return [*case.gold_cover, *(source for source in case.source_ids if source not in selected)]
    if policy != "dynamic_frontier":
        raise ValueError(f"Unknown policy: {policy}")

    sequence: list[str] = []
    selected: set[str] = set()
    while len(sequence) < len(case.source_ids):
        current = case.evaluate(selected)
        remaining = [source for source in case.source_ids if source not in selected]
        source_id = max(
            remaining,
            key=lambda source: case.dynamic_score(frozenset(selected), source, current),
        )
        selected.add(source_id)
        sequence.append(source_id)
    return sequence


def quantile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def bootstrap_mean(values: Sequence[float], samples: int, seed: int) -> dict:
    point = statistics.fmean(values) if values else 0.0
    rng = random.Random(seed)
    draws = [
        statistics.fmean(rng.choice(values) for _ in values) if values else 0.0
        for _ in range(samples)
    ]
    return {
        "value": point,
        "ci95": [quantile(draws, 0.025), quantile(draws, 0.975)],
    }


def aggregate_policy(
    cases: Sequence[ReplayCase],
    policy: str,
    random_seeds: Sequence[int],
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> tuple[dict, dict[str, dict], list[dict]]:
    per_case_runs: dict[str, list[dict]] = defaultdict(list)
    detailed_runs: list[dict] = []
    seeds = random_seeds if policy == "random" else [None]
    for case in cases:
        for seed in seeds:
            sequence = policy_sequence(case, policy, seed)
            run = run_sequence(case, sequence)
            per_case_runs[case.case_id].append(run)
            detailed_runs.append(
                {
                    "dataset": case.dataset,
                    "case_id": case.case_id,
                    "policy": policy,
                    "seed": seed,
                    "sequence": sequence,
                    "sequence_sha256": hashlib.sha256(
                        "\n".join(sequence).encode("utf-8")
                    ).hexdigest(),
                    **run,
                }
            )

    budget_metrics = {}
    for budget_index, budget in enumerate(("MAC", "2xMAC", "3xMAC_cap_N")):
        trial_values = [
            float(run["success_at"][budget])
            for runs in per_case_runs.values()
            for run in runs
        ]
        case_values = [
            statistics.fmean(float(run["success_at"][budget]) for run in runs)
            for runs in per_case_runs.values()
        ]
        estimate = bootstrap_mean(
            case_values,
            bootstrap_samples,
            bootstrap_seed + budget_index + sum(map(ord, policy)),
        )
        budget_metrics[budget] = {
            **estimate,
            "successful_trials": int(sum(trial_values)),
            "total_trials": len(trial_values),
        }

    ratios = [
        run["first_proof_over_MAC"]
        for runs in per_case_runs.values()
        for run in runs
    ]
    productive_rates = [
        run["productive_reveal_rate_until_proof"]
        for runs in per_case_runs.values()
        for run in runs
    ]
    progress_rates = [
        run["all_closure_items_per_reveal_until_proof"]
        for runs in per_case_runs.values()
        for run in runs
    ]
    aggregate = {
        "runs_per_case": len(seeds),
        "verified_answer_recovery": budget_metrics,
        "sources_to_first_proof_over_MAC": {
            "median": statistics.median(ratios),
            "p90": quantile(ratios, 0.9),
        },
        "productive_reveal_rate_until_proof": statistics.fmean(productive_rates),
        "all_closure_items_per_reveal_until_proof": statistics.fmean(progress_rates),
    }
    compact_cases = {
        case_id: {
            "first_proof_over_MAC_mean": statistics.fmean(
                run["first_proof_over_MAC"] for run in runs
            ),
            "success_at_mean": {
                budget: statistics.fmean(
                    float(run["success_at"][budget]) for run in runs
                )
                for budget in ("MAC", "2xMAC", "3xMAC_cap_N")
            },
        }
        for case_id, runs in per_case_runs.items()
    }
    return aggregate, compact_cases, detailed_runs


def paired_contrast(
    left: dict[str, dict],
    right: dict[str, dict],
    budget: str,
    bootstrap_samples: int,
    seed: int,
) -> dict:
    case_ids = sorted(set(left) & set(right))
    differences = [
        left[case_id]["success_at_mean"][budget]
        - right[case_id]["success_at_mean"][budget]
        for case_id in case_ids
    ]
    return {"budget": budget, **bootstrap_mean(differences, bootstrap_samples, seed)}


def transposition_census(
    cases: Sequence[ReplayCase], depth: int, cap: int, selection_seed: str
) -> dict:
    chosen = sorted(
        cases, key=lambda case: stable_key(selection_seed, case.case_id)
    )[:cap]
    tree_nodes = 0
    safe_states = 0
    closure_only_states = 0
    per_case = []
    for case in chosen:
        actual_depth = min(depth, len(case.source_ids))
        local_tree = sum(
            math.perm(len(case.source_ids), level) for level in range(actual_depth + 1)
        )
        subsets = [
            frozenset(subset)
            for level in range(actual_depth + 1)
            for subset in itertools.combinations(case.source_ids, level)
        ]
        signatures = {case.evaluate(subset).closure_signature for subset in subsets}
        local_safe = len(subsets)
        local_closure = len(signatures)
        tree_nodes += local_tree
        safe_states += local_safe
        closure_only_states += local_closure
        per_case.append(
            {
                "case_id": case.case_id,
                "candidate_sources": len(case.source_ids),
                "depth": actual_depth,
                "ordered_prefix_nodes": local_tree,
                "safe_subset_states": local_safe,
                "closure_only_states": local_closure,
            }
        )
    return {
        "cases": len(chosen),
        "depth": depth,
        "ordered_prefix_nodes": tree_nodes,
        "safe_subset_states": safe_states,
        "order_duplication_upper_bound": 1 - safe_states / tree_nodes,
        "closure_only_states": closure_only_states,
        "closure_signature_collision_rate": 1 - closure_only_states / safe_states,
        "warning": (
            "This is a combinatorial upper bound, not an observed TT hit rate or "
            "an MCGS result. Closure-signature collisions retain different source "
            "coverage/action masks and must not be merged by closure alone."
        ),
        "per_case": per_case,
    }


def run_clutrr_sanity(config: dict, root: Path) -> dict:
    repo = root / "repo"
    release = root / "paper_data" / "data_emnlp_final" / "data_089907f8"
    _rules, surface, composition, inverse, symmetric, equivalence = clutrr.load_program(repo)
    selected = []
    input_files = []
    for hop in config["selection"]["k_hops"]:
        csv_path = release / f"1.{hop}_test.csv"
        input_files.append(csv_path)
        frame = clutrr.pd.read_csv(csv_path)
        eligible = []
        for _row_id, row in frame.iterrows():
            story_edges = ast.literal_eval(row["story_edges"])
            clean_types = ast.literal_eval(row["edge_types"])
            clean_edges = story_edges[: len(clean_types)]
            facts = {
                (source, surface[predicate], target)
                for (source, target), predicate in zip(clean_edges, clean_types)
            }
            query_edge = ast.literal_eval(row["query_edge"])
            query = (query_edge[0], surface[str(row["target"])], query_edge[1])
            known, ranks = clutrr.closure(
                facts, composition, inverse, symmetric, equivalence
            )
            if query in known and ranks[query] >= config["selection"]["minimum_query_round"]:
                eligible.append((row, len(facts), len(known), ranks[query]))
        chosen = sorted(
            eligible,
            key=lambda item: stable_key(
                config_root["selection_seed"], "clutrr", item[0]["id"]
            ),
        )[: config["selection"]["per_hop"]]
        if len(chosen) != config["selection"]["per_hop"]:
            raise AssertionError(f"Insufficient CLUTRR k={hop} sanity cases")
        selected.extend(chosen)
    if len(selected) != config["sample_size"]:
        raise AssertionError("CLUTRR sample size mismatch")
    return {
        "role": config["role"],
        "cases": len(selected),
        "verified_queries": len(selected),
        "verified_rate": 1.0,
        "query_round_median": statistics.median(item[3] for item in selected),
        "source_fact_median": statistics.median(item[1] for item in selected),
        "closure_fact_median": statistics.median(item[2] for item in selected),
        "selection_pressure": "none in the clean release (candidate/clean = 1)",
        "case_ids": [str(item[0]["id"]) for item in selected],
        "input_files": [str(path.relative_to(NAACL_ROOT)) for path in input_files],
    }


def dataset_summary(cases: Sequence[ReplayCase]) -> dict:
    candidate_counts = [len(case.source_ids) for case in cases]
    covers = [case.minimum_cover for case in cases]
    ratios = [len(case.source_ids) / case.minimum_cover for case in cases]
    return {
        "cases": len(cases),
        "candidate_sources": {
            "median": statistics.median(candidate_counts),
            "min": min(candidate_counts),
            "max": max(candidate_counts),
        },
        "minimum_source_cover": {
            "median": statistics.median(covers),
            "min": min(covers),
            "max": max(covers),
        },
        "candidate_to_cover_ratio": {
            "median": statistics.median(ratios),
            "min": min(ratios),
            "max": max(ratios),
        },
    }


def run_dataset(cases: Sequence[ReplayCase], config: dict) -> tuple[dict, list[dict]]:
    aggregates = {}
    case_results = {}
    detailed_trials: list[dict] = []
    for policy in config["policies"]:
        aggregate, compact, trials = aggregate_policy(
            cases,
            policy,
            config["random_seeds"],
            config["bootstrap_samples"],
            config["bootstrap_seed"],
        )
        aggregates[policy] = aggregate
        case_results[policy] = compact
        detailed_trials.extend(trials)
    contrasts = {
        "dynamic_minus_random_at_2xMAC": paired_contrast(
            case_results["dynamic_frontier"],
            case_results["random"],
            "2xMAC",
            config["bootstrap_samples"],
            config["bootstrap_seed"] + 101,
        ),
        "dynamic_minus_static_at_2xMAC": paired_contrast(
            case_results["dynamic_frontier"],
            case_results["static_surface"],
            "2xMAC",
            config["bootstrap_samples"],
            config["bootstrap_seed"] + 202,
        ),
    }
    result = {
        "sample": dataset_summary(cases),
        "policies": aggregates,
        "paired_descriptive_contrasts": contrasts,
        "transposition_census": transposition_census(
            cases,
            config["transposition_depth"],
            config["transposition_case_cap_per_dataset"],
            config["transposition_selection_seed"],
        ),
        "selected_cases": [
            {
                "case_id": case.case_id,
                "minimum_cover": case.minimum_cover,
                **case.metadata,
            }
            for case in cases
        ],
    }
    return result, detailed_trials


def git_state() -> dict:
    root = NAACL_ROOT.parent
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
    )
    return {"commit": commit, "workspace_dirty": dirty}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=SCRIPT_PATH.with_name("config.json"))
    parser.add_argument(
        "--output",
        type=Path,
        default=SCRIPT_PATH.parent / "results" / "experiment_v1_results.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=SCRIPT_PATH.parent / "results" / "experiment_v1_manifest.json",
    )
    parser.add_argument(
        "--trials",
        type=Path,
        default=SCRIPT_PATH.parent / "results" / "experiment_v1_trials.jsonl",
    )
    args = parser.parse_args()

    global config_root
    config_root = json.loads(args.config.read_text(encoding="utf-8"))
    pw_config = config_root["datasets"]["proofwriter_d5"]
    step_config = config_root["datasets"]["stepgame"]
    clutrr_config = config_root["datasets"]["clutrr"]
    pw_path = NAACL_ROOT / pw_config["path"]
    step_path = NAACL_ROOT / step_config["test_path"]
    template_path = NAACL_ROOT / step_config["template_path"]
    clutrr_root = NAACL_ROOT / clutrr_config["root"]

    proofwriter_cases = select_proofwriter_cases(pw_config, pw_path)
    stepgame_cases = select_stepgame_cases(step_config, step_path, template_path)
    proofwriter_result, proofwriter_trials = run_dataset(
        proofwriter_cases, config_root
    )
    stepgame_result, stepgame_trials = run_dataset(stepgame_cases, config_root)
    trial_rows = sorted(
        [*proofwriter_trials, *stepgame_trials],
        key=lambda row: (
            row["dataset"],
            row["case_id"],
            row["policy"],
            -1 if row["seed"] is None else row["seed"],
        ),
    )
    args.trials.parent.mkdir(parents=True, exist_ok=True)
    args.trials.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in trial_rows
        ),
        encoding="utf-8",
    )

    results = {
        "schema_version": 1,
        "run_id": config_root["run_id"],
        "run_date": config_root["run_date"],
        "run_status": "complete",
        "evidence_status": config_root["status"],
        "evidence_mode": config_root["evidence_mode"],
        "free_access_model": config_root["free_access_model"],
        "disclosure": config_root["claim_boundary"],
        "config_sha256": sha256_file(args.config),
        "trial_artifact": {
            "path": str(args.trials.relative_to(NAACL_ROOT)),
            "rows": len(trial_rows),
            "sha256": sha256_file(args.trials),
        },
        "datasets": {
            "proofwriter_d5": proofwriter_result,
            "stepgame": stepgame_result,
            "clutrr": run_clutrr_sanity(clutrr_config, clutrr_root),
        },
        "interpretation_guardrails": {
            "supported": [
                "released/oracle symbolic replay reaches exact closure on three benchmark families",
                "source acquisition is nontrivial on two curated hard slices under the frozen free-text/entity-index access model",
                "a surface-only dynamic frontier is directly comparable with static and random ordering on those slices",
                "the acquisition lattice contains a measurable combinatorial order-duplication upper bound",
            ],
            "not_supported": config_root["not_tested"],
            "next_gate": (
                "Replace gold replay with a frozen noisy parser/outcome model, then compare "
                "Greedy, Beam, TreeMCTS, and state-sharing MCGS under equal paid access."
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(results))

    audit_dependencies = [
        AUDIT_ROOT / "audit_productive_recursion.py",
        AUDIT_ROOT / "audit_stepgame.py",
        AUDIT_ROOT / "audit_clutrr.py",
        clutrr_root / "repo" / "clutrr" / "store" / "rules_store.yaml",
        clutrr_root / "repo" / "clutrr" / "store" / "relations_store.yaml",
    ]
    input_paths = [pw_path, step_path, template_path, *audit_dependencies]
    for relative in results["datasets"]["clutrr"]["input_files"]:
        input_paths.append(NAACL_ROOT / relative)
    manifest = {
        "schema_version": 1,
        "run_id": config_root["run_id"],
        "run_date": config_root["run_date"],
        "config": {
            "path": str(args.config.relative_to(NAACL_ROOT)),
            "sha256": sha256_file(args.config),
        },
        "runner": {
            "path": str(SCRIPT_PATH.relative_to(NAACL_ROOT)),
            "sha256": sha256_file(SCRIPT_PATH),
        },
        "result": {
            "path": str(args.output.relative_to(NAACL_ROOT)),
            "sha256": sha256_file(args.output),
        },
        "trials": {
            "path": str(args.trials.relative_to(NAACL_ROOT)),
            "rows": len(trial_rows),
            "sha256": sha256_file(args.trials),
        },
        "inputs": [
            {
                "path": str(path.relative_to(NAACL_ROOT)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(set(input_paths))
        ],
        "git": git_state(),
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "pandas": importlib.metadata.version("pandas"),
            "networkx": importlib.metadata.version("networkx"),
            "pyyaml": importlib.metadata.version("PyYAML"),
            "clutrr_repository_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=clutrr_root / "repo",
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip(),
        },
        "determinism": (
            "Selection, policy seeds, bootstraps, JSON ordering, executor code, rule stores, "
            "and runtime versions are frozen. Re-running the listed files in this runtime "
            "must reproduce the result and trial hashes."
        ),
    }
    args.manifest.write_bytes(canonical_json_bytes(manifest))
    print(json.dumps({
        "result": str(args.output),
        "result_sha256": manifest["result"]["sha256"],
        "trial_rows": len(trial_rows),
        "proofwriter_cases": len(proofwriter_cases),
        "stepgame_cases": len(stepgame_cases),
        "clutrr_cases": results["datasets"]["clutrr"]["cases"],
    }, indent=2))


if __name__ == "__main__":
    main()
