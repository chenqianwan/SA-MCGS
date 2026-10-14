#!/usr/bin/env python3
"""Audit official StepGame as a confirmatory recursive-closure corpus.

The parser is derived from the official ``template.py`` inventory and the
generator's argument substitutions.  It never uses the gold label to choose
between ambiguous surface templates.  Spatial facts are represented as exact
2-D offset constraints; qualitative labels are recovered only after closure.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import itertools
import json
import math
import re
import statistics
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import networkx as nx


REPO_COMMIT = "5e6aff1563a6d7f46ee1f1aeff98b94e68c29005"
EXPECTED_HASHES = {
    "test": "8fd1a61d36257322752f39e412d7aff1a187a555a30414a10c1bae66acd112bc",
    "generator": "5144f62caf6adcca80ae282c02693a49b842e6150487aed50c624f2239a244c5",
    "template": "c9ff684b7674a2c8c11af6d584619c24786d704d6eaa031d28d50e3983db0c02",
}

FUNCTION_VECTORS = {
    "object1_left_object2": (-1, 0),
    "object1_right_object2": (1, 0),
    "object1_over_object2": (0, 1),
    "object1_below_object2": (0, -1),
    "object1_lowerleft_object2": (-1, -1),
    "object1_upright_object2": (1, 1),
    "object1_lowerright_object2": (1, -1),
    "object1_upleft_object2": (-1, 1),
}

# In these functions the template's AA is object1; the remaining functions
# write object1 as BB and reverse the replacement order in official code.
AA_IS_OBJECT1 = {
    "object1_left_object2",
    "object1_over_object2",
    "object1_lowerleft_object2",
    "object1_lowerright_object2",
}

QUESTION_RE = re.compile(
    r"^What is the relation of the agent (?P<source>[A-Z]) "
    r"to the agent (?P<target>[A-Z])\?$"
)

VALID_LABELS = {
    "left",
    "right",
    "above",
    "below",
    "upper-left",
    "upper-right",
    "lower-left",
    "lower-right",
    "overlap",
}

# A normalized constraint (a, b, dx, dy) means pos(a) - pos(b) = (dx, dy),
# with a < b solely to merge inverse-equivalent source expressions.
Constraint = tuple[str, str, int, int]
RawEdge = tuple[str, str, int, int]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_constraint(source: str, target: str, dx: int, dy: int) -> Constraint:
    if source < target:
        return source, target, dx, dy
    return target, source, -dx, -dy


def offset_label(dx: int, dy: int) -> str:
    if dy > 0:
        if dx < 0:
            return "upper-left"
        if dx > 0:
            return "upper-right"
        return "above"
    if dy < 0:
        if dx < 0:
            return "lower-left"
        if dx > 0:
            return "lower-right"
        return "below"
    if dx < 0:
        return "left"
    if dx > 0:
        return "right"
    return "overlap"


@dataclass(frozen=True)
class CompiledTemplate:
    pattern: re.Pattern[str]
    function: str
    index: int
    vector: tuple[int, int]
    fields: frozenset[str]
    surface_template: str


@dataclass(frozen=True)
class SentenceParse:
    status: str
    constraints: tuple[Constraint, ...]
    raw_edges: tuple[RawEdge, ...]
    signatures: tuple[str, ...]


class OfficialTemplateParser:
    def __init__(self, template_path: Path) -> None:
        self.templates = self._compile(template_path)

    @staticmethod
    def _compile(template_path: Path) -> list[CompiledTemplate]:
        tree = ast.parse(template_path.read_text(encoding="utf-8"))
        compiled: list[CompiledTemplate] = []
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name not in FUNCTION_VECTORS:
                continue
            candidates: list[str] = []
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if any(
                    isinstance(target, ast.Name) and target.id == "template_candidates"
                    for target in statement.targets
                ):
                    candidates = ast.literal_eval(statement.value)
                    break
            bindings = (
                {"AA": "source", "BB": "target"}
                if node.name in AA_IS_OBJECT1
                else {"BB": "source", "AA": "target"}
            )
            for index, template in enumerate(candidates):
                fields: set[str] = set()
                regex = ""
                for part in re.split(r"(AA|BB)", template):
                    if part not in bindings:
                        regex += re.escape(part)
                        continue
                    field = bindings[part]
                    if field in fields:
                        regex += f"(?P={field})"
                    else:
                        regex += f"(?P<{field}>[A-Z])"
                        fields.add(field)
                compiled.append(
                    CompiledTemplate(
                        pattern=re.compile(f"^{regex}$"),
                        function=node.name,
                        index=index,
                        vector=FUNCTION_VECTORS[node.name],
                        fields=frozenset(fields),
                        surface_template=template,
                    )
                )
        return compiled

    def parse(self, sentence: str) -> SentenceParse:
        complete: set[RawEdge] = set()
        signatures: set[str] = set()
        incomplete = False
        for template in self.templates:
            match = template.pattern.fullmatch(sentence)
            if match is None:
                continue
            signature = f"{template.function}[{template.index}]={template.vector}"
            signatures.add(signature)
            if not {"source", "target"}.issubset(template.fields):
                incomplete = True
                continue
            source = match.group("source")
            target = match.group("target")
            dx, dy = template.vector
            complete.add((source, target, dx, dy))

        constraints = tuple(
            sorted({normalize_constraint(*edge) for edge in complete})
        )
        if len(constraints) == 1:
            status = "canonical"
        elif len(constraints) > 1:
            status = "ambiguous"
        elif incomplete:
            status = "incomplete_template"
        else:
            status = "unmatched"
        return SentenceParse(
            status=status,
            constraints=constraints,
            raw_edges=tuple(sorted(complete)),
            signatures=tuple(sorted(signatures)),
        )


def adjacency(
    constraints: Sequence[Constraint], *, with_edge_ids: bool = False
) -> dict[str, list]:
    graph: dict[str, list] = defaultdict(list)
    for edge_id, (a, b, dx, dy) in enumerate(constraints):
        if with_edge_ids:
            graph[b].append((a, dx, dy, edge_id))
            graph[a].append((b, -dx, -dy, edge_id))
        else:
            graph[b].append((a, dx, dy))
            graph[a].append((b, -dx, -dy))
    return graph


def solve_constraints(
    constraints: Sequence[Constraint],
) -> tuple[dict[str, tuple[int, int]], dict[str, int], bool]:
    graph = adjacency(constraints)
    coordinates: dict[str, tuple[int, int]] = {}
    component: dict[str, int] = {}
    consistent = True
    component_id = 0
    for root in graph:
        if root in coordinates:
            continue
        coordinates[root] = (0, 0)
        component[root] = component_id
        queue = deque([root])
        while queue:
            current = queue.popleft()
            x, y = coordinates[current]
            for neighbor, dx, dy in graph[current]:
                expected = (x + dx, y + dy)
                if neighbor not in coordinates:
                    coordinates[neighbor] = expected
                    component[neighbor] = component_id
                    queue.append(neighbor)
                elif coordinates[neighbor] != expected:
                    consistent = False
        component_id += 1
    return coordinates, component, consistent


def query_label(
    constraints: Sequence[Constraint], source: str, target: str
) -> tuple[str | None, bool]:
    coordinates, component, consistent = solve_constraints(constraints)
    if source not in component or target not in component or component[source] != component[target]:
        return None, consistent
    source_xy = coordinates[source]
    target_xy = coordinates[target]
    return offset_label(source_xy[0] - target_xy[0], source_xy[1] - target_xy[1]), consistent


def shortest_path_with_edges(
    constraints: Sequence[Constraint], source: str, target: str
) -> tuple[int | None, list[int]]:
    graph = adjacency(constraints, with_edge_ids=True)
    queue = deque([source])
    predecessor: dict[str, tuple[str, int] | None] = {source: None}
    while queue and target not in predecessor:
        current = queue.popleft()
        for neighbor, _dx, _dy, edge_id in graph.get(current, []):
            if neighbor in predecessor:
                continue
            predecessor[neighbor] = (current, edge_id)
            queue.append(neighbor)
    if target not in predecessor:
        return None, []
    path_edges: list[int] = []
    current = target
    while predecessor[current] is not None:
        previous, edge_id = predecessor[current]
        path_edges.append(edge_id)
        current = previous
    path_edges.reverse()
    return len(path_edges), path_edges


def connected_without_edge(
    graph: dict[str, list], source: str, target: str, skipped_edge: int
) -> bool:
    seen = {source}
    stack = [source]
    while stack:
        current = stack.pop()
        for neighbor, _dx, _dy, edge_id in graph.get(current, []):
            if edge_id == skipped_edge or neighbor in seen:
                continue
            if neighbor == target:
                return True
            seen.add(neighbor)
            stack.append(neighbor)
    return source == target


def connected_components(graph: nx.Graph) -> list[set[str]]:
    return [set(component) for component in nx.connected_components(graph)]


def canonical_story_metrics(
    constraints: Sequence[Constraint], query_source: str, query_target: str, gold: str
) -> dict:
    simple = nx.Graph((a, b) for a, b, _dx, _dy in constraints)
    multigraph = nx.MultiGraph()
    for edge_id, (a, b, _dx, _dy) in enumerate(constraints):
        multigraph.add_edge(a, b, key=edge_id, edge_id=edge_id)

    distance, support_edges = shortest_path_with_edges(
        constraints, query_source, query_target
    )
    if distance is None:
        raise ValueError("Fully parsed official story did not connect its query entities")
    query_nodes = set(nx.node_connected_component(simple, query_source))
    query_edge_ids = [
        edge_id
        for edge_id, (a, b, _dx, _dy) in enumerate(constraints)
        if a in query_nodes and b in query_nodes
    ]
    query_cycle_rank = len(query_edge_ids) - len(query_nodes) + 1
    components = connected_components(simple)
    total_cycle_rank = len(constraints) - simple.number_of_nodes() + len(components)

    diameters = [nx.diameter(simple.subgraph(component)) for component in components]
    fixed_point_rounds = max(max(diameters, default=0) - 1, 0)
    closure_ordered_pairs = sum(len(component) * (len(component) - 1) for component in components)
    base_ordered_pairs = 2 * len(set(constraints))
    productive_closure_facts = closure_ordered_pairs - base_ordered_pairs

    graph_with_ids = adjacency(constraints, with_edge_ids=True)
    critical_edges = [
        edge_id
        for edge_id in query_edge_ids
        if not connected_without_edge(
            graph_with_ids, query_source, query_target, edge_id
        )
    ]
    support_constraints = [constraints[edge_id] for edge_id in support_edges]
    support_label, support_consistent = query_label(
        support_constraints, query_source, query_target
    )
    all_label, all_consistent = query_label(constraints, query_source, query_target)

    return {
        "candidate_sources": len(constraints),
        "minimum_support_sources": distance,
        "minimum_support_fraction": distance / len(constraints),
        "candidate_to_minimum_support_ratio": len(constraints) / distance,
        "nominal_distractor_sources": len(constraints) - distance,
        "sources_outside_query_component": len(constraints) - len(query_edge_ids),
        "sources_inside_query_component_not_in_one_minimum_proof": len(query_edge_ids)
        - distance,
        "query_recursive_rounds_after_base": max(distance - 1, 0),
        "story_fixed_point_rounds_after_base": fixed_point_rounds,
        "closure_ordered_pairs": closure_ordered_pairs,
        "base_ordered_pairs_after_transposition": base_ordered_pairs,
        "productive_new_ordered_pairs": productive_closure_facts,
        "query_is_productive_multihop": distance > 1,
        "story_closure_is_productive": productive_closure_facts > 0,
        "undirected_source_cycle_rank": total_cycle_rank,
        "query_component_cycle_rank": query_cycle_rank,
        "but_for_critical_sources": len(critical_edges),
        "noncritical_source_deletions_preserving_derivability": len(constraints)
        - len(critical_edges),
        "one_minimum_proof_is_sufficient": support_consistent and support_label == gold,
        "full_story_consistent": all_consistent,
        "full_story_label": all_label,
    }


def orientation_metrics(
    raw_edges: Sequence[RawEdge], query_source: str, query_target: str
) -> dict:
    directed = nx.DiGraph((source, target) for source, target, _dx, _dy in raw_edges)
    components = [
        component
        for component in nx.strongly_connected_components(directed)
        if len(component) > 1
    ]
    directed_path = (
        query_source in directed
        and query_target in directed
        and nx.has_path(directed, query_source, query_target)
    )

    # Lexicographically minimize (source hops, inverse/transposition steps).
    neighbors: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for source, target, _dx, _dy in raw_edges:
        neighbors[source].append((target, 0))
        neighbors[target].append((source, 1))
    frontier = [(0, 0, query_source)]
    best = {query_source: (0, 0)}
    while frontier:
        frontier.sort(reverse=True)
        hops, inversions, current = frontier.pop()
        if best.get(current) != (hops, inversions):
            continue
        if current == query_target:
            break
        for neighbor, inverse_cost in neighbors.get(current, []):
            candidate = (hops + 1, inversions + inverse_cost)
            if candidate < best.get(neighbor, (math.inf, math.inf)):
                best[neighbor] = candidate
                frontier.append((*candidate, neighbor))
    min_hops, min_inversions = best[query_target]
    return {
        "directed_source_path_without_transposition": directed_path,
        "minimum_source_hops": min_hops,
        "minimum_inverse_steps_among_shortest_paths": min_inversions,
        "shortest_proof_requires_transposition": min_inversions > 0,
        "nontrivial_directed_sccs": len(components),
        "largest_directed_scc": max(map(len, components), default=0),
    }


def describe(values: Sequence[float | int]) -> dict:
    if not values:
        return {"count": 0}
    ordered = sorted(values)

    def percentile(p: float) -> float:
        position = (len(ordered) - 1) * p
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return float(ordered[lower])
        weight = position - lower
        return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)

    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 6),
        "median": round(float(statistics.median(values)), 6),
        "p90": round(percentile(0.9), 6),
        "max": max(values),
    }


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def parse_question(question: str) -> tuple[str, str] | None:
    match = QUESTION_RE.fullmatch(question)
    if match is None:
        return None
    return match.group("source"), match.group("target")


def ambiguity_labels(
    parses: Sequence[SentenceParse], query_source: str, query_target: str
) -> tuple[set[str], int]:
    fixed = [item.constraints[0] for item in parses if item.status == "canonical"]
    alternatives = [item.constraints for item in parses if item.status == "ambiguous"]
    possible: set[str] = set()
    valid_assignments = 0
    for choices in itertools.product(*alternatives) if alternatives else [()]:
        constraints = fixed + list(choices)
        label, consistent = query_label(constraints, query_source, query_target)
        if not consistent:
            continue
        valid_assignments += 1
        if label is not None:
            possible.add(label)
    return possible, valid_assignments


def empty_bucket() -> dict:
    return {
        "counts": Counter(),
        "sentence_status": Counter(),
        "story_sentences": [],
        "nominal_noise": [],
        "minimum_support": [],
        "candidate_to_support": [],
        "query_rounds": [],
        "story_rounds": [],
        "critical_sources": [],
    }


def audit(test_path: Path, template_path: Path) -> dict:
    parser = OfficialTemplateParser(template_path)
    counts = Counter()
    sentence_status = Counter()
    label_counts = Counter()
    hop_counts = Counter()
    ambiguity_signatures = Counter()
    incomplete_signatures = Counter()
    possible_label_set_sizes = Counter()
    metrics: dict[str, list] = defaultdict(list)
    per_hop = defaultdict(empty_bucket)

    with test_path.open(encoding="utf-8") as handle:
        for line in handle:
            example = json.loads(line)
            counts["examples"] += 1
            hop = int(example["k_hop"])
            hop_key = str(hop)
            hop_counts[hop_key] += 1
            label = example["label"]
            label_counts[label] += 1
            if label not in VALID_LABELS:
                counts["invalid_labels"] += 1

            story = example["story"]
            bucket = per_hop[hop_key]
            bucket["counts"]["examples"] += 1
            bucket["story_sentences"].append(len(story))
            bucket["nominal_noise"].append(len(story) - hop)
            metrics["story_sentences"].append(len(story))
            metrics["nominal_noise"].append(len(story) - hop)

            question = parse_question(example["question"])
            if question is None:
                counts["question_parse_failures"] += 1
                continue
            counts["questions_parsed"] += 1
            query_source, query_target = question

            parses = [parser.parse(sentence) for sentence in story]
            counts["story_sentences"] += len(parses)
            for sentence, item in zip(story, parses):
                sentence_status[item.status] += 1
                bucket["sentence_status"][item.status] += 1
                if item.status == "ambiguous":
                    ambiguity_signatures[" | ".join(item.signatures)] += 1
                elif item.status == "incomplete_template":
                    incomplete_signatures[" | ".join(item.signatures)] += 1

            full_canonical = all(item.status == "canonical" for item in parses)
            orientation_clean = full_canonical and all(
                len(item.raw_edges) == 1 for item in parses
            )
            counts["examples_fully_canonical"] += full_canonical
            counts["examples_orientation_clean"] += orientation_clean
            bucket["counts"]["fully_canonical"] += full_canonical
            bucket["counts"]["orientation_clean"] += orientation_clean

            # Conservative reconstruction uses only facts with one canonical
            # constraint and simply drops unresolved sentences.
            strict_constraints = [
                item.constraints[0] for item in parses if item.status == "canonical"
            ]
            strict_label, strict_consistent = query_label(
                strict_constraints, query_source, query_target
            )
            counts["strict_partial_graph_consistent"] += strict_consistent
            if strict_label is not None:
                counts["query_reconstructable_from_unique_facts"] += 1
                bucket["counts"]["query_reconstructable_from_unique_facts"] += 1
                if strict_label == label:
                    counts["unique_fact_query_label_matches"] += 1
                    bucket["counts"]["unique_fact_query_label_matches"] += 1

            # Set-valued parsing exposes ambiguity without using the label to
            # pick a template origin.
            possible_labels, valid_assignments = ambiguity_labels(
                parses, query_source, query_target
            )
            possible_label_set_sizes[str(len(possible_labels))] += 1
            counts["valid_template_assignments"] += valid_assignments
            if len(possible_labels) == 1:
                counts["query_label_identifiable_without_gold"] += 1
                bucket["counts"]["query_label_identifiable_without_gold"] += 1
                if next(iter(possible_labels)) == label:
                    counts["identifiable_query_label_matches"] += 1
                    bucket["counts"]["identifiable_query_label_matches"] += 1
            elif len(possible_labels) > 1:
                counts["query_label_underdetermined"] += 1
                bucket["counts"]["query_label_underdetermined"] += 1
            else:
                counts["query_not_reconstructable_from_template_facts"] += 1
                bucket["counts"]["query_not_reconstructable_from_template_facts"] += 1
            if label in possible_labels:
                counts["gold_label_in_possible_set"] += 1

            if not full_canonical:
                continue
            constraints = [item.constraints[0] for item in parses]
            story_result = canonical_story_metrics(
                constraints, query_source, query_target, label
            )
            counts["fully_canonical_graphs_consistent"] += story_result[
                "full_story_consistent"
            ]
            counts["fully_canonical_label_matches"] += (
                story_result["full_story_label"] == label
            )
            for key in (
                "candidate_sources",
                "minimum_support_sources",
                "minimum_support_fraction",
                "candidate_to_minimum_support_ratio",
                "nominal_distractor_sources",
                "sources_outside_query_component",
                "sources_inside_query_component_not_in_one_minimum_proof",
                "query_recursive_rounds_after_base",
                "story_fixed_point_rounds_after_base",
                "closure_ordered_pairs",
                "base_ordered_pairs_after_transposition",
                "productive_new_ordered_pairs",
                "undirected_source_cycle_rank",
                "query_component_cycle_rank",
                "but_for_critical_sources",
                "noncritical_source_deletions_preserving_derivability",
            ):
                metrics[key].append(story_result[key])
            counts["productive_multihop_queries"] += story_result[
                "query_is_productive_multihop"
            ]
            counts["stories_with_productive_closure"] += story_result[
                "story_closure_is_productive"
            ]
            counts["stories_with_undirected_source_cycle"] += (
                story_result["undirected_source_cycle_rank"] > 0
            )
            counts["query_components_with_cycle"] += (
                story_result["query_component_cycle_rank"] > 0
            )
            counts["stories_with_zero_but_for_sources"] += (
                story_result["but_for_critical_sources"] == 0
            )
            counts["minimum_proof_sufficiency_checks_passed"] += story_result[
                "one_minimum_proof_is_sufficient"
            ]
            counts["source_deletion_checks"] += story_result["candidate_sources"]
            counts["but_for_source_deletions"] += story_result[
                "but_for_critical_sources"
            ]
            counts["noncritical_source_deletions"] += story_result[
                "noncritical_source_deletions_preserving_derivability"
            ]

            bucket["counts"]["productive_multihop_queries"] += story_result[
                "query_is_productive_multihop"
            ]
            bucket["counts"]["undirected_cycle"] += (
                story_result["undirected_source_cycle_rank"] > 0
            )
            bucket["counts"]["zero_critical_sources"] += (
                story_result["but_for_critical_sources"] == 0
            )
            bucket["minimum_support"].append(
                story_result["minimum_support_sources"]
            )
            bucket["candidate_to_support"].append(
                story_result["candidate_to_minimum_support_ratio"]
            )
            bucket["query_rounds"].append(
                story_result["query_recursive_rounds_after_base"]
            )
            bucket["story_rounds"].append(
                story_result["story_fixed_point_rounds_after_base"]
            )
            bucket["critical_sources"].append(
                story_result["but_for_critical_sources"]
            )

            if orientation_clean:
                raw_edges = [item.raw_edges[0] for item in parses]
                oriented = orientation_metrics(
                    raw_edges, query_source, query_target
                )
                counts["orientation_clean_directed_path_without_transposition"] += oriented[
                    "directed_source_path_without_transposition"
                ]
                counts["orientation_clean_shortest_proof_requires_transposition"] += oriented[
                    "shortest_proof_requires_transposition"
                ]
                counts["orientation_clean_stories_with_directed_source_scc"] += (
                    oriented["nontrivial_directed_sccs"] > 0
                )
                metrics["minimum_inverse_steps"].append(
                    oriented["minimum_inverse_steps_among_shortest_paths"]
                )
                metrics["largest_directed_source_scc"].append(
                    oriented["largest_directed_scc"]
                )

    examples = counts["examples"]
    sentences = counts["story_sentences"]
    full = counts["examples_fully_canonical"]
    orientation_clean_count = counts["examples_orientation_clean"]
    per_hop_output = {}
    for hop_key in sorted(per_hop, key=int):
        bucket = per_hop[hop_key]
        bucket_examples = bucket["counts"]["examples"]
        bucket_full = bucket["counts"]["fully_canonical"]
        per_hop_output[hop_key] = {
            "examples": bucket_examples,
            "story_sentences": describe(bucket["story_sentences"]),
            "nominal_noise_sentences": describe(bucket["nominal_noise"]),
            "sentence_parse_status": dict(sorted(bucket["sentence_status"].items())),
            "fully_canonical_examples": bucket_full,
            "fully_canonical_rate": ratio(bucket_full, bucket_examples),
            "query_reconstructable_from_unique_facts_rate": ratio(
                bucket["counts"]["query_reconstructable_from_unique_facts"],
                bucket_examples,
            ),
            "query_label_identifiable_without_gold_rate": ratio(
                bucket["counts"]["query_label_identifiable_without_gold"],
                bucket_examples,
            ),
            "minimum_support_sources_on_fully_canonical": describe(
                bucket["minimum_support"]
            ),
            "candidate_to_minimum_support_ratio_on_fully_canonical": describe(
                bucket["candidate_to_support"]
            ),
            "query_recursive_rounds_on_fully_canonical": describe(
                bucket["query_rounds"]
            ),
            "story_fixed_point_rounds_on_fully_canonical": describe(
                bucket["story_rounds"]
            ),
            "productive_multihop_query_rate_on_fully_canonical": ratio(
                bucket["counts"]["productive_multihop_queries"], bucket_full
            ),
            "undirected_source_cycle_rate_on_fully_canonical": ratio(
                bucket["counts"]["undirected_cycle"], bucket_full
            ),
            "zero_but_for_source_rate_on_fully_canonical": ratio(
                bucket["counts"]["zero_critical_sources"], bucket_full
            ),
        }

    return {
        "dataset_counts": {
            "examples": examples,
            "story_sentences": sentences,
            "k_hop_distribution": dict(sorted(hop_counts.items())),
            "label_distribution": dict(sorted(label_counts.items())),
            "invalid_labels": counts["invalid_labels"],
        },
        "official_template_inventory": {
            "compiled_templates": len(parser.templates),
            "functions": len(FUNCTION_VECTORS),
            "canonical_vectors": {
                function: list(vector)
                for function, vector in sorted(FUNCTION_VECTORS.items())
            },
        },
        "parse_coverage": {
            "questions_parsed": counts["questions_parsed"],
            "question_parse_rate": ratio(counts["questions_parsed"], examples),
            "sentence_status": dict(sorted(sentence_status.items())),
            "sentence_canonical_rate_after_inverse_equivalence": ratio(
                sentence_status["canonical"], sentences
            ),
            "sentence_genuinely_ambiguous_rate": ratio(
                sentence_status["ambiguous"], sentences
            ),
            "sentence_incomplete_template_rate": ratio(
                sentence_status["incomplete_template"], sentences
            ),
            "fully_canonical_examples": full,
            "fully_canonical_example_rate": ratio(full, examples),
            "orientation_clean_examples": orientation_clean_count,
            "orientation_clean_example_rate": ratio(
                orientation_clean_count, examples
            ),
            "ambiguous_template_signatures": dict(
                ambiguity_signatures.most_common()
            ),
            "incomplete_template_signatures": dict(
                incomplete_signatures.most_common()
            ),
            "warning": (
                "Official template provenance is required for this recovery. Some emitted "
                "strings correspond to multiple generator actions, and one template drops an entity."
            ),
        },
        "query_label_consistency": {
            "reconstructable_from_only_unique_facts": counts[
                "query_reconstructable_from_unique_facts"
            ],
            "unique_fact_reconstruction_matches_gold": counts[
                "unique_fact_query_label_matches"
            ],
            "unique_fact_match_rate_when_reconstructable": ratio(
                counts["unique_fact_query_label_matches"],
                counts["query_reconstructable_from_unique_facts"],
            ),
            "possible_label_set_size_distribution": dict(
                sorted(possible_label_set_sizes.items(), key=lambda item: int(item[0]))
            ),
            "identifiable_without_gold": counts[
                "query_label_identifiable_without_gold"
            ],
            "identifiable_without_gold_rate": ratio(
                counts["query_label_identifiable_without_gold"], examples
            ),
            "identifiable_labels_matching_gold": counts[
                "identifiable_query_label_matches"
            ],
            "identifiable_match_rate": ratio(
                counts["identifiable_query_label_matches"],
                counts["query_label_identifiable_without_gold"],
            ),
            "underdetermined_without_gold": counts["query_label_underdetermined"],
            "not_reconstructable_from_available_template_facts": counts[
                "query_not_reconstructable_from_template_facts"
            ],
            "gold_in_possible_label_set": counts["gold_label_in_possible_set"],
            "fully_canonical_label_matches": counts[
                "fully_canonical_label_matches"
            ],
            "fully_canonical_label_match_rate": ratio(
                counts["fully_canonical_label_matches"], full
            ),
        },
        "minimum_support_and_noise": {
            "scope": "fully canonical stories only",
            "candidate_sources": describe(metrics["candidate_sources"]),
            "minimum_support_sources": describe(metrics["minimum_support_sources"]),
            "minimum_support_fraction": describe(metrics["minimum_support_fraction"]),
            "candidate_to_minimum_support_ratio": describe(
                metrics["candidate_to_minimum_support_ratio"]
            ),
            "nominal_noise_sentences_all_examples": describe(metrics["nominal_noise"]),
            "sources_outside_query_component": describe(
                metrics["sources_outside_query_component"]
            ),
            "sources_inside_query_component_not_in_one_minimum_proof": describe(
                metrics["sources_inside_query_component_not_in_one_minimum_proof"]
            ),
        },
        "recursive_closure": {
            "formalization": {
                "edb": "source_offset(x,y,dx,dy) acquired from each natural-language sentence",
                "inverse_rule": "offset(y,x,-dx,-dy) :- source_offset(x,y,dx,dy)",
                "recursive_rule": (
                    "offset(x,z,dx1+dx2,dy1+dy2) :- offset(x,y,dx1,dy1), "
                    "base_offset(y,z,dx2,dy2)"
                ),
                "label_projection": "sign(dx), sign(dy) -> one of nine qualitative labels",
                "round_semantics": (
                    "Round 0 materializes source facts plus inverses; each synchronous round "
                    "extends a known path by one base edge."
                ),
                "predicate_dependency_scc": ["offset"],
                "recursive_predicate_self_scc": True,
                "rules_are_global_and_natural_language_rules_per_instance": False,
                "natural_language_acquisition_target": "facts only",
            },
            "query_recursive_rounds_after_base": describe(
                metrics["query_recursive_rounds_after_base"]
            ),
            "story_fixed_point_rounds_after_base": describe(
                metrics["story_fixed_point_rounds_after_base"]
            ),
            "productive_multihop_queries": counts["productive_multihop_queries"],
            "productive_multihop_query_rate": ratio(
                counts["productive_multihop_queries"], full
            ),
            "stories_with_productive_closure": counts[
                "stories_with_productive_closure"
            ],
            "productive_story_rate": ratio(
                counts["stories_with_productive_closure"], full
            ),
            "productive_new_ordered_pairs": describe(
                metrics["productive_new_ordered_pairs"]
            ),
        },
        "source_cycles_and_transposition": {
            "scope_for_undirected_cycles": "fully canonical stories",
            "stories_with_undirected_source_cycle": counts[
                "stories_with_undirected_source_cycle"
            ],
            "undirected_source_cycle_rate": ratio(
                counts["stories_with_undirected_source_cycle"], full
            ),
            "undirected_cycle_rank": describe(
                metrics["undirected_source_cycle_rank"]
            ),
            "query_components_with_cycle": counts["query_components_with_cycle"],
            "scope_for_orientation": "orientation-clean stories only",
            "directed_path_without_transposition": counts[
                "orientation_clean_directed_path_without_transposition"
            ],
            "directed_path_without_transposition_rate": ratio(
                counts["orientation_clean_directed_path_without_transposition"],
                orientation_clean_count,
            ),
            "shortest_proof_requires_transposition": counts[
                "orientation_clean_shortest_proof_requires_transposition"
            ],
            "shortest_proof_requires_transposition_rate": ratio(
                counts["orientation_clean_shortest_proof_requires_transposition"],
                orientation_clean_count,
            ),
            "minimum_inverse_steps_among_shortest_paths": describe(
                metrics["minimum_inverse_steps"]
            ),
            "stories_with_nontrivial_directed_source_scc": counts[
                "orientation_clean_stories_with_directed_source_scc"
            ],
            "directed_source_scc_rate": ratio(
                counts["orientation_clean_stories_with_directed_source_scc"],
                orientation_clean_count,
            ),
            "largest_directed_source_scc": describe(
                metrics["largest_directed_source_scc"]
            ),
            "interpretation": (
                "Predicate recursion is universal, but most instance source graphs are trees/DAG-like; "
                "supporting noise creates some undirected alternate-path cycles."
            ),
        },
        "deletion_causality": {
            "scope": "fully canonical stories; delete one natural-language source fact at a time",
            "source_deletion_checks": counts["source_deletion_checks"],
            "but_for_source_deletions_breaking_query_derivability": counts[
                "but_for_source_deletions"
            ],
            "but_for_deletion_rate": ratio(
                counts["but_for_source_deletions"], counts["source_deletion_checks"]
            ),
            "noncritical_source_deletions_preserving_derivability": counts[
                "noncritical_source_deletions"
            ],
            "but_for_critical_sources_per_story": describe(
                metrics["but_for_critical_sources"]
            ),
            "stories_with_zero_but_for_sources": counts[
                "stories_with_zero_but_for_sources"
            ],
            "minimum_proof_sufficiency_checks_passed": counts[
                "minimum_proof_sufficiency_checks_passed"
            ],
            "minimum_proof_sufficiency_rate": ratio(
                counts["minimum_proof_sufficiency_checks_passed"], full
            ),
            "interpretation": (
                "But-for edges test source causality; zero-critical stories have redundant/alternate paths, "
                "while a selected shortest source set must remain sufficient on its own."
            ),
        },
        "by_k_hop": per_hop_output,
        "benchmark_verdict": {
            "use_as_second_confirmatory_corpus_after_proofwriter": True,
            "recommended_role": (
                "Confirm domain transfer of NL fact acquisition, temporary-KB accumulation, "
                "recursive closure, proof selection, and robustness to irrelevant/redundant sources."
            ),
            "does_not_confirm": [
                "natural-language rule acquisition",
                "real-world provenance or contradiction handling",
                "nontrivial predicate-SCC structure beyond one recursive offset predicate",
                "SCC-specific search difficulty on most instance graphs",
            ],
            "critical_caveats": [
                "Synthetic entities and globally fixed spatial algebra make the rules known in advance.",
                "Only facts, not rules, are acquired from natural language per instance.",
                "Official templates still contain ambiguous and entity-dropping surface forms.",
                "Use full-canonical or label-identifiable subsets and publish the filtering script.",
            ],
        },
    }


def main() -> None:
    audit_dir = Path(__file__).resolve().parent
    default_raw = audit_dir / "raw" / "logic" / "stepgame"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test", type=Path, default=default_raw / "test.jsonl"
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=default_raw / "repo" / "Code" / "template.py",
    )
    parser.add_argument(
        "--generator",
        type=Path,
        default=default_raw
        / "repo"
        / "Code"
        / "parameterized_step_game_8relation.py",
    )
    parser.add_argument(
        "--output", type=Path, default=audit_dir / "stepgame_audit.json"
    )
    args = parser.parse_args()

    files = {
        "test": args.test,
        "template": args.template,
        "generator": args.generator,
    }
    source_files = {}
    for name, path in files.items():
        actual_hash = sha256_file(path)
        if actual_hash != EXPECTED_HASHES[name]:
            raise ValueError(
                f"Unexpected {name} SHA256: {actual_hash}; expected {EXPECTED_HASHES[name]}"
            )
        source_files[name] = {
            "path": path.resolve().relative_to(audit_dir).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": actual_hash,
        }

    result = {
        "schema_version": 1,
        "audit_as_of": "2026-08-18",
        "generated_by": Path(__file__).name,
        "source": {
            "name": "StepGame TrainVersion noisy test split",
            "official_repository": "https://github.com/ShiZhengyan/StepGame",
            "repository_commit": REPO_COMMIT,
            "immutable_test_url": (
                "https://raw.githubusercontent.com/ShiZhengyan/StepGame/"
                f"{REPO_COMMIT}/Dataset/TrainVersion/test.jsonl"
            ),
            "primary_paper": "https://ojs.aaai.org/index.php/AAAI/article/view/21383",
            "license": "MIT repository license",
            "license_url": (
                "https://github.com/ShiZhengyan/StepGame/blob/"
                f"{REPO_COMMIT}/LICENSE"
            ),
            "files": source_files,
        },
        "audit": audit(args.test, args.template),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
