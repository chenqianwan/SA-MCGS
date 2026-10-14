#!/usr/bin/env python3
"""Generate the deterministic V3 A0 SCC-scaling mechanism benchmark.

The benchmark is deliberately synthetic.  It isolates predicate-ring topology
from finite-ground Horn derivation depth; it is not confirmatory evidence about
natural corpora or LLM parsing quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence


SCRIPT_PATH = Path(__file__).resolve()
EXPERIMENT_ROOT = SCRIPT_PATH.parent
DEFAULT_CONFIG = EXPERIMENT_ROOT / "config.json"
ORACLE_VERSION = "finite-ground-positive-horn-v1"

PREDICATE_WORDS = (
    "amber", "brisk", "calm", "dapper", "eager", "faint", "gentle",
    "hardy", "ivory", "jolly", "keen", "lucid", "mellow", "nimble",
    "ochre", "proud", "quiet", "rosy", "solar", "tidy", "umber",
    "vivid", "warm", "young", "zesty", "agile", "bright", "crisp",
    "dusky", "even", "fresh", "grand", "humble", "icy", "kind",
    "lively", "misty", "noble", "pale", "rapid", "soft", "tawny",
    "vast", "wise",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_seed(*parts: object) -> int:
    payload = "|".join(map(str, parts)).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def atom(predicate: str, argument: str) -> dict[str, Any]:
    return {"predicate": predicate, "arguments": [argument]}


def atom_key(value: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    return value["predicate"], tuple(value["arguments"])


def atom_from_key(value: tuple[str, tuple[str, ...]]) -> dict[str, Any]:
    return {"predicate": value[0], "arguments": list(value[1])}


def atom_label(value: dict[str, Any]) -> str:
    return f"{value['predicate']}({','.join(value['arguments'])})"


def entity_surface(value: str) -> str:
    return value[0].upper() + value[1:]


def fact_text(head: dict[str, Any]) -> str:
    return f"{entity_surface(head['arguments'][0])} is {head['predicate']}."


def rule_text(body: Sequence[dict[str, Any]], head: dict[str, Any]) -> str:
    premises = " and ".join(
        f"{entity_surface(item['arguments'][0])} is {item['predicate']}"
        for item in body
    )
    return (
        f"If {premises}, then {entity_surface(head['arguments'][0])} "
        f"is {head['predicate']}."
    )


def make_fact_source(
    source_id: str,
    head: dict[str, Any],
    role: str,
    *,
    is_distractor: bool,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "kind": "fact",
        "text": fact_text(head),
        "role": role,
        "is_distractor": is_distractor,
        "formal": {"kind": "fact", "head": head, "body": []},
    }


def make_rule_source(
    source_id: str,
    body: Sequence[dict[str, Any]],
    head: dict[str, Any],
    role: str,
    *,
    is_distractor: bool,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "kind": "rule",
        "text": rule_text(body, head),
        "role": role,
        "is_distractor": is_distractor,
        "formal": {"kind": "rule", "head": head, "body": list(body)},
    }


def saturate(
    sources: Sequence[dict[str, Any]],
    excluded_source_ids: Iterable[str] = (),
    extra_facts: Sequence[dict[str, Any]] = (),
) -> tuple[
    set[tuple[str, tuple[str, ...]]],
    dict[tuple[str, tuple[str, ...]], int],
    dict[tuple[str, tuple[str, ...]], dict[str, Any]],
]:
    """Independent synchronous least-fixed-point oracle."""

    excluded = set(excluded_source_ids)
    closure: set[tuple[str, tuple[str, ...]]] = set()
    ranks: dict[tuple[str, tuple[str, ...]], int] = {}
    provenance: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    rules = []
    for source in sorted(sources, key=lambda item: item["source_id"]):
        if source["source_id"] in excluded:
            continue
        formal = source["formal"]
        if formal["kind"] == "fact":
            key = atom_key(formal["head"])
            closure.add(key)
            ranks[key] = 0
            provenance.setdefault(
                key,
                {"source_id": source["source_id"], "premises": []},
            )
        else:
            rules.append(source)
    for index, value in enumerate(extra_facts):
        key = atom_key(value)
        closure.add(key)
        ranks[key] = 0
        provenance.setdefault(
            key,
            {"source_id": f"__oracle_extra_fact_{index}", "premises": []},
        )

    round_number = 0
    while True:
        round_number += 1
        candidates: dict[
            tuple[str, tuple[str, ...]], list[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]]]
        ] = defaultdict(list)
        for source in rules:
            formal = source["formal"]
            head = atom_key(formal["head"])
            body = tuple(atom_key(item) for item in formal["body"])
            if head not in closure and all(item in closure for item in body):
                candidates[head].append((source["source_id"], body))
        if not candidates:
            break
        for head, alternatives in sorted(candidates.items()):
            source_id, body = min(alternatives)
            closure.add(head)
            ranks[head] = round_number
            provenance[head] = {
                "source_id": source_id,
                "premises": [atom_from_key(item) for item in body],
            }
    return closure, ranks, provenance


def proof_source_ids(
    target: tuple[str, tuple[str, ...]],
    provenance: dict[tuple[str, tuple[str, ...]], dict[str, Any]],
) -> list[str]:
    ordered: list[str] = []
    visited: set[tuple[str, tuple[str, ...]]] = set()

    def visit(current: tuple[str, tuple[str, ...]]) -> None:
        if current in visited:
            return
        visited.add(current)
        item = provenance[current]
        for premise in item["premises"]:
            visit(atom_key(premise))
        if not item["source_id"].startswith("__oracle_"):
            ordered.append(item["source_id"])

    visit(target)
    return ordered


def strongly_connected_components(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> list[set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    node_set = set(nodes)
    self_loops: set[str] = set()
    for source, target in edges:
        node_set.update((source, target))
        adjacency[source].add(target)
        if source == target:
            self_loops.add(source)

    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in sorted(adjacency.get(node, ())):
            if nxt not in indices:
                visit(nxt)
                lowlinks[node] = min(lowlinks[node], lowlinks[nxt])
            elif nxt in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[nxt])
        if lowlinks[node] == indices[node]:
            component: set[str] = set()
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.add(member)
                if member == node:
                    break
            components.append(component)

    for node in sorted(node_set):
        if node not in indices:
            visit(node)
    return [
        component
        for component in components
        if len(component) > 1 or any(node in self_loops for node in component)
    ]


def build_graph(
    sources: Sequence[dict[str, Any]], query_atom: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    predicate_nodes = {query_atom["predicate"]}
    predicate_edges = []
    predicate_edge_pairs = []
    for source in sources:
        formal = source["formal"]
        predicate_nodes.add(formal["head"]["predicate"])
        for premise in formal["body"]:
            predicate_nodes.add(premise["predicate"])
            predicate_edges.append(
                {
                    "from": premise["predicate"],
                    "to": formal["head"]["predicate"],
                    "source_id": source["source_id"],
                }
            )
            predicate_edge_pairs.append(
                (premise["predicate"], formal["head"]["predicate"])
            )

    source_edges = []
    ground_edges = []
    adjacency: dict[str, set[str]] = {
        source["source_id"]: set() for source in sources
    }
    for producer in sources:
        producer_head = producer["formal"]["head"]
        for consumer in sources:
            if producer["source_id"] == consumer["source_id"]:
                continue
            for premise in consumer["formal"]["body"]:
                if producer_head["predicate"] == premise["predicate"]:
                    edge = {
                        "from_source_id": producer["source_id"],
                        "to_source_id": consumer["source_id"],
                        "matched_predicate": premise["predicate"],
                    }
                    source_edges.append(edge)
                    adjacency[producer["source_id"]].add(consumer["source_id"])
                    if atom_key(producer_head) == atom_key(premise):
                        ground_edges.append(edge)

    source_pairs = [
        (edge["from_source_id"], edge["to_source_id"])
        for edge in source_edges
    ]
    predicate_sccs = strongly_connected_components(predicate_nodes, predicate_edge_pairs)
    source_sccs = strongly_connected_components(adjacency, source_pairs)
    graph = {
        "predicate_nodes": sorted(predicate_nodes),
        "predicate_edges": sorted(
            predicate_edges,
            key=lambda item: (item["from"], item["to"], item["source_id"]),
        ),
        "source_edges": sorted(
            source_edges,
            key=lambda item: (
                item["from_source_id"],
                item["to_source_id"],
                item["matched_predicate"],
            ),
        ),
        "ground_dependency_edges": sorted(
            ground_edges,
            key=lambda item: (
                item["from_source_id"],
                item["to_source_id"],
                item["matched_predicate"],
            ),
        ),
        "recursive_predicate_components": [
            sorted(component)
            for component in sorted(predicate_sccs, key=lambda value: sorted(value))
        ],
        "recursive_source_components": [
            sorted(component)
            for component in sorted(source_sccs, key=lambda value: sorted(value))
        ],
    }
    return graph, {key: sorted(value) for key, value in sorted(adjacency.items())}


def family_predicates(seed: int, size: int, family_index: int) -> tuple[list[str], str]:
    rng = random.Random(stable_seed(seed, "predicates", size, family_index))
    words = list(PREDICATE_WORDS)
    rng.shuffle(words)
    return words[:size], words[size]


def build_distractors(
    size: int,
    family_index: int,
    core_predicates: Sequence[str],
    count: int,
) -> list[dict[str, Any]]:
    distractors = []
    tag = f"s{size:02d}f{family_index:02d}"
    for index in range(count):
        source_id = f"src_dist_{index:03d}"
        entity = f"dummy{tag}d{index:03d}"
        auxiliary = f"aux{tag}d{index:03d}"
        core = core_predicates[(index * 7 + family_index) % size]
        mode = index % 5
        if mode == 0:
            source = make_fact_source(
                source_id,
                atom(f"{core}hint{tag}d{index:03d}", entity),
                "lexical_near_core_distractor_fact",
                is_distractor=True,
            )
        elif mode == 1:
            source = make_rule_source(
                source_id,
                [atom(auxiliary, entity)],
                atom(core, entity),
                "one_way_incoming_distractor_rule",
                is_distractor=True,
            )
        elif mode == 2:
            source = make_rule_source(
                source_id,
                [atom(core, entity)],
                atom(auxiliary, entity),
                "one_way_outgoing_distractor_rule",
                is_distractor=True,
            )
        elif mode == 3:
            source = make_fact_source(
                source_id,
                atom(auxiliary, entity),
                "independent_distractor_fact",
                is_distractor=True,
            )
        else:
            source = make_rule_source(
                source_id,
                [atom(auxiliary, entity)],
                atom(f"tail{tag}d{index:03d}", entity),
                "independent_distractor_rule",
                is_distractor=True,
            )
        distractors.append(source)
    return distractors


def build_case(
    config: dict[str, Any],
    size: int,
    family_index: int,
    condition: str,
    core_predicates: Sequence[str],
    split_predicate: str,
    distractors: Sequence[dict[str, Any]],
    distractor_multiplier: int,
) -> dict[str, Any]:
    tag = f"s{size:02d}f{family_index:02d}"
    family_id = f"v3-{tag}"
    case_id = f"{family_id}-{condition}"
    seed_entity = f"aria{tag}"
    query_entity = f"borin{tag}"
    query = atom(core_predicates[0], query_entity)

    uses_split_seed = condition in {"unseeded_scc", "matched_dag"}
    seed_predicate = split_predicate if uses_split_seed else core_predicates[0]
    seed_role = "inactive_seed_control" if condition == "unseeded_scc" else "seed"
    core_sources = [
        make_fact_source(
            "src_core_seed",
            atom(seed_predicate, seed_entity),
            seed_role,
            is_distractor=False,
        )
    ]
    for index in range(size):
        source_id = f"src_core_rule_{index:03d}"
        if index == 0:
            body_predicate = (
                split_predicate if condition == "matched_dag" else core_predicates[0]
            )
            body = [atom(body_predicate, seed_entity)]
            head = atom(core_predicates[1], seed_entity)
            role = "dag_chain_rule" if condition == "matched_dag" else "scc_internal_rule"
        elif index < size - 1:
            body = [atom(core_predicates[index], seed_entity)]
            head = atom(core_predicates[index + 1], seed_entity)
            role = "dag_chain_rule" if condition == "matched_dag" else "scc_internal_rule"
        else:
            body = [atom(core_predicates[-1], seed_entity)]
            head = query
            role = "dag_terminal_rule" if condition == "matched_dag" else "scc_closing_rule"
        core_sources.append(
            make_rule_source(source_id, body, head, role, is_distractor=False)
        )

    sources = [*core_sources, *json.loads(json.dumps(distractors))]
    order_rng = random.Random(
        stable_seed(config["fixed_seed"], "source-order", size, family_index)
    )
    source_ids = [source["source_id"] for source in sources]
    order_rng.shuffle(source_ids)
    by_id = {source["source_id"]: source for source in sources}
    sources = [by_id[source_id] for source_id in source_ids]
    graph, source_adjacency = build_graph(sources, query)

    closure, ranks, provenance = saturate(sources)
    target = atom_key(query)
    entailed = target in closure
    causal_sources = []
    if entailed:
        for source_id in source_ids:
            reduced, _, _ = saturate(sources, excluded_source_ids=[source_id])
            if target not in reduced:
                causal_sources.append(source_id)
        proof_ids = proof_source_ids(target, provenance)
    else:
        proof_ids = []

    derivation_steps = []
    for derived, rank in sorted(ranks.items(), key=lambda item: (item[1], item[0])):
        support = provenance[derived]
        derivation_steps.append(
            {
                "round": rank,
                "atom": atom_from_key(derived),
                "source_id": support["source_id"],
                "premises": support["premises"],
            }
        )

    predicate_scc_sizes = [
        len(component) for component in graph["recursive_predicate_components"]
    ]
    source_scc_sizes = [
        len(component) for component in graph["recursive_source_components"]
    ]
    reference_cover = size + 1
    real_budget = min(
        len(sources),
        config["budget"]["real_action_multiplier_over_reference_cover"]
        * reference_cover,
    )
    counterfactual_rank = None
    if condition == "unseeded_scc":
        counterfactual_closure, counterfactual_ranks, _ = saturate(
            sources,
            extra_facts=[atom(core_predicates[0], seed_entity)],
        )
        if target in counterfactual_closure:
            counterfactual_rank = counterfactual_ranks[target]

    topology = "chain" if condition == "matched_dag" else "ring"
    return {
        "schema_version": config["schema_version"],
        "benchmark_id": config["benchmark_id"],
        "evidence_status": config["evidence_status"],
        "formal_profile": config["formal_profile"],
        "case_id": case_id,
        "family_id": family_id,
        "family_index": family_index,
        "condition": condition,
        "scc_size": size,
        "actual_recursive_scc_size": max(predicate_scc_sizes, default=0),
        "actual_recursive_source_scc_size": max(source_scc_sizes, default=0),
        "designed_depth": size,
        "label": "entailed" if entailed else "unknown",
        "query_atom": query,
        "query_text": f"Is {entity_surface(query_entity)} {core_predicates[0]}?",
        "root_source_id": "src_core_seed",
        "start_source_id": "src_core_seed",
        "source_ids": source_ids,
        "sources": sources,
        "source_adjacency": source_adjacency,
        "graph": {
            **graph,
            "physical_topology": topology,
            "claim_scope": "A0 synthetic ring/chain mechanism probe; not confirmatory",
        },
        "budget": {
            "real_action_budget": real_budget,
            "reference_proof_sources": reference_cover,
            "total_sources": len(sources),
            "distractor_sources": len(distractors),
            "distractor_multiplier": distractor_multiplier,
        },
        "gold": {
            "oracle_version": ORACLE_VERSION,
            "query_entailed": entailed,
            "query_rank": ranks.get(target),
            "counterfactual_query_rank_with_relevant_seed": counterfactual_rank,
            "closure_atoms": [atom_from_key(value) for value in sorted(closure)],
            "proof_source_ids": proof_ids,
            "deletion_causal_source_ids": sorted(causal_sources),
            "closing_rule_source_id": f"src_core_rule_{size - 1:03d}",
            "derivation_steps": derivation_steps,
        },
        "pairing": {
            "family_id": family_id,
            "conditions": list(config["conditions"]),
            "core_predicates": list(core_predicates),
            "split_predicate": split_predicate,
            "split_method": "seed-side occurrence of closing predicate only",
            "hard_matches": list(config["matched_control"]["hard_matches"]),
        },
    }


def validate_case(case: dict[str, Any]) -> None:
    sources = case["sources"]
    source_ids = case["source_ids"]
    assert len(source_ids) == len(set(source_ids)) == len(sources)
    assert {source["source_id"] for source in sources} == set(source_ids)
    assert case["root_source_id"] in source_ids
    assert set(case["source_adjacency"]) == set(source_ids)
    assert case["budget"]["total_sources"] == len(sources)
    assert case["budget"]["distractor_sources"] == sum(
        source["is_distractor"] for source in sources
    )
    assert case["budget"]["distractor_sources"] == (
        case["budget"]["distractor_multiplier"]
        * case["budget"]["reference_proof_sources"]
    )
    for source in sources:
        formal = source["formal"]
        assert formal["kind"] in {"fact", "rule"}
        assert formal["kind"] == source["kind"]
        assert len(formal["head"]["arguments"]) == 1
        assert not formal["head"]["predicate"].startswith("not_")
        if formal["kind"] == "fact":
            assert formal["body"] == []
        else:
            assert formal["body"]
        for premise in formal["body"]:
            assert len(premise["arguments"]) == 1
            assert not premise["predicate"].startswith("not_")

    condition = case["condition"]
    size = case["scc_size"]
    target = atom_key(case["query_atom"])
    closure, ranks, _ = saturate(sources)
    assert case["gold"]["query_entailed"] == (target in closure)
    assert case["gold"]["query_rank"] == ranks.get(target)
    assert case["gold"]["closure_atoms"] == [
        atom_from_key(value) for value in sorted(closure)
    ]
    core_ids = {"src_core_seed"} | {
        f"src_core_rule_{index:03d}" for index in range(size)
    }
    closing_id = f"src_core_rule_{size - 1:03d}"
    if condition in {"productive_seeded_scc", "matched_dag"}:
        assert target in closure
        assert ranks[target] == size
        assert set(case["gold"]["proof_source_ids"]) == core_ids
        assert set(case["gold"]["deletion_causal_source_ids"]) == core_ids
        assert closing_id in case["gold"]["deletion_causal_source_ids"]
        without_closing, _, _ = saturate(sources, excluded_source_ids=[closing_id])
        closing_source = next(
            source for source in sources if source["source_id"] == closing_id
        )
        assert target not in without_closing
        assert all(atom_key(item) in without_closing for item in closing_source["formal"]["body"])
    else:
        assert condition == "unseeded_scc"
        assert target not in closure
        core_predicates = set(case["pairing"]["core_predicates"])
        assert not any(value[0] in core_predicates for value in closure)
        empty_seed_closure, _, _ = saturate(
            [source for source in sources if source["kind"] == "rule"]
        )
        assert target not in empty_seed_closure
        assert case["gold"]["counterfactual_query_rank_with_relevant_seed"] == size
        assert case["gold"]["proof_source_ids"] == []
        assert case["gold"]["deletion_causal_source_ids"] == []

    if condition == "matched_dag":
        assert case["graph"]["physical_topology"] == "chain"
        assert case["actual_recursive_scc_size"] == 0
        assert case["actual_recursive_source_scc_size"] == 0
    else:
        assert case["graph"]["physical_topology"] == "ring"
        assert case["actual_recursive_scc_size"] == size
        assert case["actual_recursive_source_scc_size"] == size


def validate_family(cases: Sequence[dict[str, Any]]) -> None:
    assert len(cases) == 3
    by_condition = {case["condition"]: case for case in cases}
    assert set(by_condition) == {
        "productive_seeded_scc", "unseeded_scc", "matched_dag"
    }
    reference = cases[0]
    for case in cases[1:]:
        assert case["family_id"] == reference["family_id"]
        assert case["scc_size"] == reference["scc_size"]
        assert case["designed_depth"] == reference["designed_depth"]
        assert case["query_atom"] == reference["query_atom"]
        assert case["query_text"] == reference["query_text"]
        assert case["source_ids"] == reference["source_ids"]
        assert case["budget"] == reference["budget"]
        assert Counter(source["kind"] for source in case["sources"]) == Counter(
            source["kind"] for source in reference["sources"]
        )
        assert [
            source for source in case["sources"] if source["is_distractor"]
        ] == [
            source for source in reference["sources"] if source["is_distractor"]
        ]
    assert by_condition["productive_seeded_scc"]["label"] == "entailed"
    assert by_condition["matched_dag"]["label"] == "entailed"
    assert by_condition["unseeded_scc"]["label"] == "unknown"


def generate(config: dict[str, Any]) -> list[dict[str, Any]]:
    assert config["conditions"] == [
        "productive_seeded_scc", "unseeded_scc", "matched_dag"
    ]
    rows = []
    for size in config["scc_sizes"]:
        assert 3 <= size < len(PREDICATE_WORDS)
        for family_index in range(config["families_per_size"]):
            core_predicates, split_predicate = family_predicates(
                config["fixed_seed"], size, family_index
            )
            multiplier_rng = random.Random(
                stable_seed(
                    config["fixed_seed"], "distractor-multiplier", size, family_index
                )
            )
            multiplier = multiplier_rng.choice(config["distractors"]["multipliers"])
            distractor_count = multiplier * (size + 1)
            distractors = build_distractors(
                size, family_index, core_predicates, distractor_count
            )
            family_cases = [
                build_case(
                    config,
                    size,
                    family_index,
                    condition,
                    core_predicates,
                    split_predicate,
                    distractors,
                    multiplier,
                )
                for condition in config["conditions"]
            ]
            for case in family_cases:
                validate_case(case)
            validate_family(family_cases)
            rows.extend(family_cases)
    return rows


def build_manifest(
    config: dict[str, Any], rows: Sequence[dict[str, Any]], data_payload: bytes
) -> dict[str, Any]:
    per_size: dict[str, Any] = {}
    for size in config["scc_sizes"]:
        selected = [row for row in rows if row["scc_size"] == size]
        per_size[str(size)] = {
            "families": len({row["family_id"] for row in selected}),
            "cases": len(selected),
            "per_condition": dict(sorted(Counter(row["condition"] for row in selected).items())),
            "source_count_min": min(row["budget"]["total_sources"] for row in selected),
            "source_count_max": max(row["budget"]["total_sources"] for row in selected),
            "designed_depth": size,
        }
    return {
        "schema_version": config["schema_version"],
        "benchmark_id": config["benchmark_id"],
        "evidence_status": config["evidence_status"],
        "generation_date": config["generation_date"],
        "fixed_seed": config["fixed_seed"],
        "generator": SCRIPT_PATH.name,
        "generator_sha256": sha256_file(SCRIPT_PATH),
        "config": DEFAULT_CONFIG.name,
        "config_sha256": sha256_file(DEFAULT_CONFIG),
        "data_file": config["output"]["jsonl"],
        "data_sha256": sha256_bytes(data_payload),
        "data_bytes": len(data_payload),
        "families": len({row["family_id"] for row in rows}),
        "cases": len(rows),
        "labels": dict(sorted(Counter(row["label"] for row in rows).items())),
        "per_condition": dict(sorted(Counter(row["condition"] for row in rows).items())),
        "per_size": per_size,
        "distractor_multiplier_cases": dict(
            sorted(Counter(str(row["budget"]["distractor_multiplier"]) for row in rows).items())
        ),
        "source_count": {
            "minimum": min(row["budget"]["total_sources"] for row in rows),
            "maximum": max(row["budget"]["total_sources"] for row in rows),
            "total_across_cases": sum(row["budget"]["total_sources"] for row in rows),
        },
        "oracle": {
            "version": ORACLE_VERSION,
            "status": "passed",
            "checked_cases": len(rows),
            "checked_families": len({row["family_id"] for row in rows}),
            "hard_checks": [
                "all statements are finite positive ground Horn",
                "productive query rank equals configured size",
                "closing SCC rule produces a previously absent query atom",
                "closing SCC rule is single-source deletion-causal",
                "every productive and matched proof source is deletion-causal",
                "unseeded SCC cannot derive the query from rules alone",
                "counterfactual relevant seed restores unseeded depth",
                "matched DAG has no recursive predicate or source SCC",
                "paired cases exactly match source/fact/rule counts, distractors, query, and designed depth"
            ],
        },
        "claim_boundary": (
            "A0 synthetic ring/chain mechanism benchmark. It is not confirmatory "
            "evidence for natural-corpus prevalence, LLM parsing, or an ACL headline claim."
        ),
        "reproduce": f"python3 {SCRIPT_PATH.name}",
    }


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Regenerate in memory, run every oracle check, and compare existing bytes.",
    )
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rows = generate(config)
    data_payload = b"".join(
        (canonical_json(row) + "\n").encode("utf-8") for row in rows
    )
    manifest = build_manifest(config, rows, data_payload)
    manifest_payload = pretty_json_bytes(manifest)
    data_path = config_path.parent / config["output"]["jsonl"]
    manifest_path = config_path.parent / config["output"]["manifest"]

    if args.check_only:
        if not data_path.exists() or not manifest_path.exists():
            raise SystemExit("Generated data or manifest is missing")
        if data_path.read_bytes() != data_payload:
            raise SystemExit("Existing benchmark.jsonl is not deterministic/current")
        if manifest_path.read_bytes() != manifest_payload:
            raise SystemExit("Existing manifest.json is not deterministic/current")
    else:
        atomic_write(data_path, data_payload)
        atomic_write(manifest_path, manifest_payload)

    print(
        json.dumps(
            {
                "status": "passed",
                "check_only": args.check_only,
                "families": manifest["families"],
                "cases": manifest["cases"],
                "data_sha256": manifest["data_sha256"],
                "data_bytes": manifest["data_bytes"],
                "data_path": str(data_path),
                "manifest_path": str(manifest_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
