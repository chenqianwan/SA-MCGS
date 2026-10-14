#!/usr/bin/env python3
"""Audit genuinely productive recursion in ProofWriter-style Horn theories.

This script deliberately separates three notions that are often conflated:

1. a cycle in the predicate dependency graph;
2. an SCC-internal rule that actually derives a new ground atom; and
3. an SCC-internal rule whose deletion removes an otherwise entailed query.

Only (3) is strong enough for the causal "productive recursion" split used by
the LFP-MCGS project.  The evaluator is a small, independent positive-Horn
reference engine; explicit negative facts are represented as separate signed
predicates, while theories containing negative/default-negated rule literals
are excluded from this audit.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence


VARIABLES = {"someone", "something"}
TOKEN_RE = re.compile(r'\(|\)|->|"(?:[^"\\]|\\.)*"')


@dataclass(frozen=True, order=True)
class Atom:
    predicate: str
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class Rule:
    rule_id: str
    body: tuple[Atom, ...]
    head: Atom


@dataclass(frozen=True)
class GroundRule:
    instance_id: str
    rule_id: str
    body: tuple[Atom, ...]
    head: Atom
    crosses_constants: bool


def parse_sexpr(text: str):
    tokens = TOKEN_RE.findall(text)
    cursor = 0

    def parse_one():
        nonlocal cursor
        token = tokens[cursor]
        cursor += 1
        if token != "(":
            if token.startswith('"'):
                return json.loads(token)
            return token
        result = []
        while tokens[cursor] != ")":
            result.append(parse_one())
        cursor += 1
        return result

    value = parse_one()
    if cursor != len(tokens):
        raise ValueError(f"Unparsed tokens in {text!r}")
    return value


def atom_from_expr(expr: Sequence[str]) -> Atom:
    if len(expr) != 4 or not all(isinstance(item, str) for item in expr):
        raise ValueError(f"Unexpected atom expression: {expr!r}")
    subject, relation, obj_or_property, polarity = expr
    if relation == "is":
        return Atom(f"{obj_or_property}::{polarity}", (subject,))
    return Atom(f"{relation}::{polarity}", (subject, obj_or_property))


def parse_rule(rule_id: str, representation: str) -> Rule:
    expr = parse_sexpr(representation)
    if len(expr) != 3 or expr[1] != "->":
        raise ValueError(f"Unexpected rule expression: {expr!r}")
    body_expr, _, head_expr = expr
    body = tuple(atom_from_expr(item) for item in body_expr)
    return Rule(rule_id, body, atom_from_expr(head_expr))


def parse_fact(representation: str) -> Atom:
    return atom_from_expr(parse_sexpr(representation))


def positive_rule_theory(raw_rules: dict, allow_explicit_negation: bool) -> bool:
    for raw_rule in raw_rules.values():
        signs = set(re.findall(r'"([+\-~])"', raw_rule["representation"]))
        allowed = {"+", "-"} if allow_explicit_negation else {"+"}
        if signs - allowed:
            return False
    return True


def predicate_sccs(rules: Sequence[Rule]) -> tuple[dict[str, int], set[int]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    predicates = set()
    self_loops = set()
    for rule in rules:
        predicates.add(rule.head.predicate)
        for premise in rule.body:
            predicates.add(premise.predicate)
            adjacency[premise.predicate].add(rule.head.predicate)
            if premise.predicate == rule.head.predicate:
                self_loops.add(premise.predicate)

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    components: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index
        indices[node] = lowlink[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in adjacency.get(node, ()):
            if nxt not in indices:
                strongconnect(nxt)
                lowlink[node] = min(lowlink[node], lowlink[nxt])
            elif nxt in on_stack:
                lowlink[node] = min(lowlink[node], indices[nxt])
        if lowlink[node] == indices[node]:
            component = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            components.append(component)

    for predicate in predicates:
        if predicate not in indices:
            strongconnect(predicate)

    component_of = {
        predicate: component_id
        for component_id, component in enumerate(components)
        for predicate in component
    }
    recursive_components = {
        component_id
        for component_id, component in enumerate(components)
        if len(component) > 1 or any(predicate in self_loops for predicate in component)
    }
    return component_of, recursive_components


def substitute(atom: Atom, assignment: dict[str, str]) -> Atom:
    return Atom(
        atom.predicate,
        tuple(assignment.get(argument, argument) for argument in atom.arguments),
    )


def ground_rules(rules: Sequence[Rule], constants: Sequence[str]) -> list[GroundRule]:
    grounded: list[GroundRule] = []
    for rule in rules:
        variables = sorted(
            {
                argument
                for atom in (*rule.body, rule.head)
                for argument in atom.arguments
                if argument in VARIABLES
            }
        )
        assignments = [dict()]
        for variable in variables:
            assignments = [
                {**assignment, variable: constant}
                for assignment in assignments
                for constant in constants
            ]
        for assignment in assignments:
            body = tuple(substitute(atom, assignment) for atom in rule.body)
            head = substitute(rule.head, assignment)
            body_constants = {argument for atom in body for argument in atom.arguments}
            head_constants = set(head.arguments)
            # Human-readable, deterministic identity for one schema grounding.
            # This is stable across runs because both keys and separators are
            # canonicalized; deletion must target this ID, not ``rule_id``.
            instance_id = rule.rule_id + "@" + json.dumps(
                assignment,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            grounded.append(
                GroundRule(
                    instance_id,
                    rule.rule_id,
                    body,
                    head,
                    crosses_constants=bool(head_constants - body_constants)
                    or bool(body_constants - head_constants),
                )
            )
    return grounded


def saturate(
    facts: Iterable[Atom],
    rules: Sequence[GroundRule],
    excluded_instance_id: str | None = None,
    excluded_rule_id: str | None = None,
) -> tuple[set[Atom], dict[Atom, int], set[str], set[str]]:
    closure = set(facts)
    rank = {fact: 0 for fact in closure}
    productive_instance_ids: set[str] = set()
    cross_constant_productive_instance_ids: set[str] = set()
    round_number = 0
    while True:
        round_number += 1
        additions: set[Atom] = set()
        for rule in rules:
            if (
                rule.instance_id == excluded_instance_id
                or rule.rule_id == excluded_rule_id
                or rule.head in closure
            ):
                continue
            if all(premise in closure for premise in rule.body):
                additions.add(rule.head)
                # Record every applicable instance in this synchronous round.
                # If two instances derive the same head, single-instance
                # deletion below correctly detects that each is redundant.
                productive_instance_ids.add(rule.instance_id)
                if rule.crosses_constants:
                    cross_constant_productive_instance_ids.add(rule.instance_id)
        if not additions:
            break
        for head in additions:
            closure.add(head)
            rank[head] = round_number
    return (
        closure,
        rank,
        productive_instance_ids,
        cross_constant_productive_instance_ids,
    )


def saturate_schema_legacy(
    facts: Iterable[Atom],
    rules: Sequence[GroundRule],
    excluded_rule_id: str | None = None,
) -> tuple[set[Atom], dict[Atom, int], set[str], set[str]]:
    """Reproduce the previous schema-level metric for audit traceability.

    The old implementation selected the first applicable grounding per new
    head in each synchronous round and then deleted all groundings sharing its
    ``rule_id``.  It is intentionally isolated here and must not be used for
    the primary ground-instance causal counts.
    """

    closure = set(facts)
    rank = {fact: 0 for fact in closure}
    productive_rule_ids: set[str] = set()
    cross_constant_productive_rule_ids: set[str] = set()
    round_number = 0
    while True:
        round_number += 1
        additions: dict[Atom, GroundRule] = {}
        for rule in rules:
            if rule.rule_id == excluded_rule_id or rule.head in closure:
                continue
            if all(premise in closure for premise in rule.body):
                additions.setdefault(rule.head, rule)
        if not additions:
            break
        for head, rule in additions.items():
            closure.add(head)
            rank[head] = round_number
            productive_rule_ids.add(rule.rule_id)
            if rule.crosses_constants:
                cross_constant_productive_rule_ids.add(rule.rule_id)
    return (
        closure,
        rank,
        productive_rule_ids,
        cross_constant_productive_rule_ids,
    )


def target_for_question(question: dict) -> Atom | None:
    answer = question.get("answer")
    if answer == "Unknown":
        return None
    atom = parse_fact(question["representation"])
    if answer is True:
        return atom
    polarity = atom.predicate.rsplit("::", 1)[1]
    complement = "-" if polarity == "+" else "+"
    return Atom(atom.predicate.rsplit("::", 1)[0] + "::" + complement, atom.arguments)


def complement(atom: Atom) -> Atom:
    name, polarity = atom.predicate.rsplit("::", 1)
    return Atom(name + "::" + ("-" if polarity == "+" else "+"), atom.arguments)


def predicted_answer(question: dict, closure: set[Atom]):
    atom = parse_fact(question["representation"])
    if atom in closure:
        return True
    if complement(atom) in closure:
        return False
    return "Unknown"


def source_unit_for_theory(theory: dict) -> str:
    return "mapped_sentence_id" if theory.get("mappings") else "record_id"


def source_ids_for_proof(
    question: dict,
    mappings: dict[str, str] | None,
) -> list[set[str]]:
    covers: list[set[str]] = []
    for proof in question.get("proofsWithIntermediates", []) or []:
        representation = proof.get("representation", "")
        record_ids = set(re.findall(r"(?:triple|rule)\d+", representation))
        source_ids = (
            {mappings.get(record_id, record_id) for record_id in record_ids}
            if mappings
            else record_ids
        )
        if source_ids:
            covers.append(source_ids)
    return covers


def minimum_source_cover(
    question: dict,
    mappings: dict[str, str] | None,
) -> int | None:
    covers = source_ids_for_proof(question, mappings)
    return min(map(len, covers)) if covers else None


def candidate_source_count(theory: dict) -> int:
    record_ids = set(theory["triples"]) | set(theory["rules"])
    mappings = theory.get("mappings")
    if mappings:
        return len({mappings.get(record_id, record_id) for record_id in record_ids})
    return len(record_ids)


def query_derivation_diagnostic(
    target: Atom,
    closure: set[Atom],
    ranks: dict[Atom, int],
    rules: Sequence[GroundRule],
    internal_instance_ids: set[str],
) -> tuple[int, int, int]:
    """Return relevant internal instances, longest chain, and round span.

    Only rank-decreasing edges of earliest-round Horn derivations are followed.
    These are provenance diagnostics; they do not establish that cyclic
    feedback structure was necessary for the derivation.
    """

    derivations_by_head: dict[Atom, list[GroundRule]] = defaultdict(list)
    for rule in rules:
        if (
            rule.head in closure
            and ranks.get(rule.head, 0) > 0
            and all(premise in closure for premise in rule.body)
            and max((ranks.get(premise, 0) for premise in rule.body), default=-1)
            < ranks[rule.head]
        ):
            derivations_by_head[rule.head].append(rule)

    relevant_internal: set[str] = set()
    pending = [target]
    visited_atoms: set[Atom] = set()
    while pending:
        atom = pending.pop()
        if atom in visited_atoms:
            continue
        visited_atoms.add(atom)
        for rule in derivations_by_head.get(atom, ()):
            if rule.instance_id in internal_instance_ids:
                relevant_internal.add(rule.instance_id)
            pending.extend(rule.body)

    longest_internal_chain: dict[Atom, int] = {}
    for atom in sorted(closure, key=lambda item: ranks.get(item, 0)):
        alternatives = []
        for rule in derivations_by_head.get(atom, ()):
            premise_depth = max(
                (longest_internal_chain.get(premise, 0) for premise in rule.body),
                default=0,
            )
            alternatives.append(
                premise_depth + int(rule.instance_id in internal_instance_ids)
            )
        longest_internal_chain[atom] = max(alternatives, default=0)

    internal_head_rounds = {
        ranks[rule.head]
        for rule in rules
        if rule.instance_id in relevant_internal and rule.head in ranks
    }
    round_span = (
        max(internal_head_rounds) - min(internal_head_rounds) + 1
        if internal_head_rounds
        else 0
    )
    return (
        len(relevant_internal),
        longest_internal_chain.get(target, 0),
        round_span,
    )


def iter_theories(paths: Sequence[str]) -> Iterator[tuple[str, dict]]:
    for path in paths:
        split = Path(path).stem.removeprefix("meta-")
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield split, json.loads(line)


def audit(paths: Sequence[str], allow_explicit_negation: bool = False) -> dict:
    summary = Counter()
    per_split: dict[str, Counter] = defaultdict(Counter)
    schema_summary = Counter()
    schema_per_split: dict[str, Counter] = defaultdict(Counter)
    query_ranks = Counter()
    ground_causal_query_ranks = Counter()
    ground_causal_source_covers = Counter()
    ground_causal_candidate_sources = Counter()
    ground_candidate_to_cover_ratios = []
    schema_causal_query_ranks = Counter()
    schema_causal_source_covers = Counter()
    schema_candidate_to_cover_ratios = []
    relevant_internal_instance_counts = Counter()
    internal_chain_lengths = Counter()
    internal_round_spans = Counter()
    observed_source_units: set[str] = set()
    theory_rows = []
    case_rows = []

    for split, theory in iter_theories(paths):
        def bump(key: str, amount: int = 1) -> None:
            summary[key] += amount
            per_split[split][key] += amount

        def bump_schema(key: str, amount: int = 1) -> None:
            schema_summary[key] += amount
            schema_per_split[split][key] += amount

        # Keep explicit zeroes so the compact JSON can be asserted directly.
        bump("reference_label_mismatches", 0)
        bump_schema("reference_label_mismatches", 0)
        observed_source_units.add(source_unit_for_theory(theory))
        bump("theories")
        bump("queries", len(theory["questions"]))
        if not positive_rule_theory(theory["rules"], allow_explicit_negation):
            continue
        bump("eligible_rule_theories")
        bump("eligible_rule_queries", len(theory["questions"]))
        if not allow_explicit_negation:
            bump("positive_rule_theories")
            bump("positive_rule_queries", len(theory["questions"]))

        facts = [parse_fact(item["representation"]) for item in theory["triples"].values()]
        rules = [
            parse_rule(rule_id, item["representation"])
            for rule_id, item in theory["rules"].items()
        ]
        component_of, recursive_components = predicate_sccs(rules)
        internal_rule_ids = {
            rule.rule_id
            for rule in rules
            if component_of.get(rule.head.predicate) in recursive_components
            and any(
                component_of.get(premise.predicate) == component_of.get(rule.head.predicate)
                for premise in rule.body
            )
        }
        if internal_rule_ids:
            bump("predicate_scc_theories")

        constants = sorted(
            {
                argument
                for atom in facts
                for argument in atom.arguments
                if argument not in VARIABLES
            }
            | {
                argument
                for rule in rules
                for atom in (*rule.body, rule.head)
                for argument in atom.arguments
                if argument not in VARIABLES
            }
        )
        grounded = ground_rules(rules, constants)
        grounded_by_id = {rule.instance_id: rule for rule in grounded}
        internal_instance_ids = {
            rule.instance_id for rule in grounded if rule.rule_id in internal_rule_ids
        }
        bump(
            "predicate_recursive_internal_ground_instances",
            len(internal_instance_ids),
        )
        (
            closure,
            ranks,
            productive_instance_ids,
            cross_constant_productive_instance_ids,
        ) = saturate(facts, grounded)
        productive_internal_instance_ids = (
            internal_instance_ids & productive_instance_ids
        )
        cross_constant_productive_internal_instance_ids = (
            internal_instance_ids & cross_constant_productive_instance_ids
        )
        bump(
            "productive_internal_ground_instances",
            len(productive_internal_instance_ids),
        )
        if productive_internal_instance_ids:
            bump("productive_internal_ground_instance_theories")
        bump(
            "cross_constant_productive_internal_ground_instances",
            len(cross_constant_productive_internal_instance_ids),
        )
        if cross_constant_productive_internal_instance_ids:
            bump("cross_constant_productive_internal_ground_instance_theories")

        # Primary causal test: remove exactly one predicate-SCC-internal ground
        # instance.  Never remove every grounding of its schema here.
        ground_deletion_drops: dict[str, set[Atom]] = {}
        bump(
            "ground_instance_deletion_tests",
            len(productive_internal_instance_ids),
        )
        for instance_id in sorted(productive_internal_instance_ids):
            reduced_closure, _, _, _ = saturate(
                facts,
                grounded,
                excluded_instance_id=instance_id,
            )
            dropped = closure - reduced_closure
            if dropped:
                ground_deletion_drops[instance_id] = dropped
        bump(
            "ground_instance_deletion_contributing_instances",
            len(ground_deletion_drops),
        )
        if ground_deletion_drops:
            bump("ground_instance_deletion_contributing_scc_theories")

        # Legacy diagnostic retained for traceability: deleting a rule schema
        # removes all of its ground instances and can overstate causal evidence.
        (
            legacy_closure,
            _,
            legacy_productive_rule_ids,
            legacy_cross_constant_productive_rule_ids,
        ) = saturate_schema_legacy(facts, grounded)
        if legacy_closure != closure:
            raise AssertionError("Ground and legacy saturators disagree on closure")
        productive_internal_rule_ids = internal_rule_ids & legacy_productive_rule_ids
        cross_constant_productive_internal_rule_ids = (
            internal_rule_ids & legacy_cross_constant_productive_rule_ids
        )
        schema_deletion_drops: dict[str, set[Atom]] = {}
        for rule_id in sorted(productive_internal_rule_ids):
            reduced_closure, _, _, _ = saturate_schema_legacy(
                facts,
                grounded,
                excluded_rule_id=rule_id,
            )
            dropped = closure - reduced_closure
            if dropped:
                schema_deletion_drops[rule_id] = dropped
        if schema_deletion_drops:
            bump_schema("schema_deletion_contributing_scc_theories")
        if cross_constant_productive_internal_rule_ids:
            bump_schema("cross_constant_productive_scc_theories")

        ground_causal_queries = 0
        ground_cross_constant_causal_queries = 0
        schema_causal_queries = 0
        schema_cross_constant_causal_queries = 0
        mappings = theory.get("mappings")
        candidate_sources = candidate_source_count(theory)
        for question_id, question in theory["questions"].items():
            if predicted_answer(question, closure) != question.get("answer"):
                bump("reference_label_mismatches")
                bump_schema("reference_label_mismatches")
            target = target_for_question(question)
            if target is None or target not in closure:
                continue
            bump("entailed_queries")
            query_ranks[str(ranks.get(target, 0))] += 1
            causal_instances = sorted(
                instance_id
                for instance_id, dropped in ground_deletion_drops.items()
                if target in dropped
            )
            schema_causal_rules = sorted(
                rule_id
                for rule_id, dropped in schema_deletion_drops.items()
                if target in dropped
            )
            source_cover = minimum_source_cover(question, mappings)

            if schema_causal_rules:
                schema_causal_queries += 1
                bump_schema("schema_deletion_causal_queries")
                schema_causal_query_ranks[str(ranks.get(target, 0))] += 1
                if source_cover is not None:
                    schema_causal_source_covers[str(source_cover)] += 1
                    schema_candidate_to_cover_ratios.append(
                        candidate_sources / source_cover
                    )
                    if source_cover >= 2:
                        bump_schema("causal_queries_source_cover_ge_2")
                    if source_cover >= 3:
                        bump_schema("causal_queries_source_cover_ge_3")
                if any(
                    rule_id in cross_constant_productive_internal_rule_ids
                    for rule_id in schema_causal_rules
                ):
                    schema_cross_constant_causal_queries += 1
                    bump_schema("cross_constant_schema_deletion_causal_queries")

            if not causal_instances:
                continue
            ground_causal_queries += 1
            bump("ground_instance_deletion_causal_queries")
            ground_causal_query_ranks[str(ranks.get(target, 0))] += 1
            ground_causal_candidate_sources[str(candidate_sources)] += 1
            if source_cover is not None:
                ground_causal_source_covers[str(source_cover)] += 1
                ground_candidate_to_cover_ratios.append(candidate_sources / source_cover)
                if source_cover >= 2:
                    bump("ground_instance_causal_queries_source_cover_ge_2")
                if source_cover >= 3:
                    bump("ground_instance_causal_queries_source_cover_ge_3")
            cross_constant = any(
                grounded_by_id[instance_id].crosses_constants
                for instance_id in causal_instances
            )
            if cross_constant:
                ground_cross_constant_causal_queries += 1
                bump("cross_constant_ground_instance_deletion_causal_queries")
            relevant_count, chain_length, round_span = query_derivation_diagnostic(
                target,
                closure,
                ranks,
                grounded,
                internal_instance_ids,
            )
            relevant_internal_instance_counts[str(relevant_count)] += 1
            internal_chain_lengths[str(chain_length)] += 1
            internal_round_spans[str(round_span)] += 1
            case_rows.append(
                {
                    "theory_id": theory["id"],
                    "split": split,
                    "question_id": question_id,
                    "answer": question["answer"],
                    "query_rank": ranks.get(target, 0),
                    "minimum_source_cover": source_cover,
                    "candidate_sources": candidate_sources,
                    "source_unit": source_unit_for_theory(theory),
                    "causal_internal_ground_instances": causal_instances,
                    "schema_causal_internal_rules_diagnostic": schema_causal_rules,
                    "cross_constant": cross_constant,
                    "query_relevant_internal_ground_instances": relevant_count,
                    "longest_internal_derivation_chain": chain_length,
                    "internal_derivation_round_span": round_span,
                }
            )

        if ground_causal_queries:
            bump("ground_instance_deletion_causal_query_theories")
        if ground_cross_constant_causal_queries:
            bump("cross_constant_ground_instance_deletion_causal_query_theories")
        if schema_causal_queries:
            bump_schema("schema_deletion_causal_query_theories")
        if schema_cross_constant_causal_queries:
            bump_schema("cross_constant_schema_deletion_causal_query_theories")
        theory_rows.append(
            {
                "theory_id": theory["id"],
                "split": split,
                "facts": len(facts),
                "rules": len(rules),
                "ground_rules": len(grounded),
                "closure_atoms": len(closure),
                "max_round": max(ranks.values(), default=0),
                "internal_rule_ids": sorted(internal_rule_ids),
                "internal_ground_instances": len(internal_instance_ids),
                "productive_internal_ground_instance_ids": sorted(
                    productive_internal_instance_ids
                ),
                "ground_instance_deletion_contributing_ids": sorted(
                    ground_deletion_drops
                ),
                "schema_deletion_contributing_rule_ids_diagnostic": sorted(
                    schema_deletion_drops
                ),
                "ground_instance_causal_queries": ground_causal_queries,
                "cross_constant_ground_instance_causal_queries": (
                    ground_cross_constant_causal_queries
                ),
            }
        )

    # Explicit zeroes make cross-dataset and per-split comparisons safe without
    # requiring callers to interpret a missing Counter key as zero.
    primary_zero_safe_keys = (
        "cross_constant_productive_internal_ground_instances",
        "cross_constant_productive_internal_ground_instance_theories",
        "cross_constant_ground_instance_deletion_causal_queries",
        "cross_constant_ground_instance_deletion_causal_query_theories",
        "reference_label_mismatches",
    )
    schema_zero_safe_keys = (
        "cross_constant_productive_scc_theories",
        "cross_constant_schema_deletion_causal_queries",
        "cross_constant_schema_deletion_causal_query_theories",
        "reference_label_mismatches",
    )
    for key in primary_zero_safe_keys:
        summary.setdefault(key, 0)
        for counts in per_split.values():
            counts.setdefault(key, 0)
    for key in schema_zero_safe_keys:
        schema_summary.setdefault(key, 0)
        for counts in schema_per_split.values():
            counts.setdefault(key, 0)

    ratio_values = sorted(ground_candidate_to_cover_ratios)
    schema_ratio_values = sorted(schema_candidate_to_cover_ratios)
    source_unit = (
        next(iter(observed_source_units))
        if len(observed_source_units) == 1
        else "mixed"
    )

    def numeric_counter(counter: Counter) -> dict[str, int]:
        return dict(sorted(counter.items(), key=lambda item: int(item[0])))

    def ratio_summary(values: list[float]) -> dict:
        return {
            "count": len(values),
            "median": values[len(values) // 2] if values else None,
            "minimum": min(values, default=None),
            "maximum": max(values, default=None),
        }

    return {
        "semantic_profile": (
            "signed_monotone_horn" if allow_explicit_negation else "strict_positive_horn"
        ),
        "source_unit": source_unit,
        "ground_instance_id_format": "<rule_id>@<canonical JSON variable assignment>",
        "input_files": list(paths),
        "summary": dict(summary),
        "per_split": {
            split: dict(counts) for split, counts in sorted(per_split.items())
        },
        "entailed_query_rank_distribution": numeric_counter(query_ranks),
        "ground_instance_causal_query_rank_distribution": numeric_counter(
            ground_causal_query_ranks
        ),
        "ground_instance_causal_minimum_source_cover_distribution": numeric_counter(
            ground_causal_source_covers
        ),
        "ground_instance_causal_candidate_source_count_distribution": numeric_counter(
            ground_causal_candidate_sources
        ),
        "ground_instance_candidate_to_minimum_cover_ratio": ratio_summary(ratio_values),
        "query_relevant_internal_derivation_diagnostic": {
            "scope": "ground-instance deletion-causal queries",
            "warning": (
                "Rank-decreasing earliest-derivation provenance only; these "
                "statistics do not establish a structural feedback effect."
            ),
            "relevant_internal_ground_instance_count_distribution": numeric_counter(
                relevant_internal_instance_counts
            ),
            "longest_internal_rule_chain_distribution": numeric_counter(
                internal_chain_lengths
            ),
            "internal_rule_round_span_distribution": numeric_counter(
                internal_round_spans
            ),
        },
        "schema_level_deletion_diagnostic": {
            "warning": (
                "Legacy diagnostic: deleting one rule_id removes every grounding "
                "of that schema and is not the primary causal metric."
            ),
            "summary": dict(schema_summary),
            "per_split": {
                split: dict(counts)
                for split, counts in sorted(schema_per_split.items())
            },
            "causal_query_rank_distribution": numeric_counter(
                schema_causal_query_ranks
            ),
            "causal_minimum_source_cover_distribution": numeric_counter(
                schema_causal_source_covers
            ),
            "candidate_to_minimum_cover_ratio": ratio_summary(schema_ratio_values),
        },
        "theories": theory_rows,
        "causal_query_index": case_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("patterns", nargs="+", help="JSONL paths or glob patterns")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--signed",
        action="store_true",
        help="Treat explicit negative literals as separate positive predicates; still exclude '~'.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Omit per-theory and per-query manifests from the tracked JSON summary.",
    )
    args = parser.parse_args()
    paths = sorted({path for pattern in args.patterns for path in glob.glob(pattern)})
    paths = [path for path in paths if "stage" not in path and "abduct" not in path]
    if not paths:
        raise SystemExit("No input files matched")
    result = audit(paths, allow_explicit_negation=args.signed)
    if args.compact:
        result.pop("theories", None)
        result.pop("causal_query_index", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print("entailed_query_rank_distribution", result["entailed_query_rank_distribution"])
    print(
        "ground_instance_causal_query_rank_distribution",
        result["ground_instance_causal_query_rank_distribution"],
    )
    print(
        "ground_instance_causal_minimum_source_cover_distribution",
        result["ground_instance_causal_minimum_source_cover_distribution"],
    )
    print(
        "ground_instance_candidate_to_minimum_cover_ratio",
        result["ground_instance_candidate_to_minimum_cover_ratio"],
    )


if __name__ == "__main__":
    main()
