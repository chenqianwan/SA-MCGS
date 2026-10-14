#!/usr/bin/env python3
"""Audit the official CLUTRR paper release for LFP-MCGS data eligibility.

The script deliberately distinguishes three graph notions:

* the global relation/predicate dependency graph induced by rules_store.yaml;
* each instance's entity/source graph;
* the monotone acquisition lattice over subsets of source facts.

It uses the released canonical facts, rules, proof_state, and query labels.  The
robustness files expose gold relation labels only for the clean proof facts; the
additional distractor edges have endpoints but not relation labels.  Therefore
exact closure and deletion tests are performed on the clean proof facts, while
candidate-cost ratios use all released story edges.
"""

from __future__ import annotations

import argparse
import ast
import glob
import hashlib
import itertools
import json
import math
import os
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import networkx as nx
import pandas as pd
import yaml


Fact = tuple[int, str, int]
Rule = tuple[str, str, str]
GroundRule = tuple[Fact, Fact, Fact]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_program(repo: Path):
    store = repo / "clutrr" / "store"
    with (store / "rules_store.yaml").open() as handle:
        rules = yaml.safe_load(handle)
    with (store / "relations_store.yaml").open() as handle:
        relations = yaml.safe_load(handle)

    surface_to_predicate = {
        spec["rel"]: predicate
        for predicate, gender_specs in relations.items()
        if isinstance(gender_specs, dict)
        for spec in gender_specs.values()
        if isinstance(spec, dict) and "rel" in spec
    }
    # The release contains the corrected spelling while relations_store.yaml
    # retains the historical "neice" typo.
    surface_to_predicate["niece"] = "un"

    composition: list[Rule] = []
    for relation_rules in rules["compositional"].values():
        for left, right_map in relation_rules.items():
            for right, head in right_map.items():
                composition.append((left, right, head))

    # These stores are operational rewrite rules, not declarative equations.
    # RelationBuilder applies only the direction encoded in rules_store.yaml.
    inverse: list[tuple[str, str]] = []
    for relation_rules in rules["inverse-equivalence"].values():
        inverse.extend(relation_rules.items())

    symmetric: list[tuple[str, str]] = []
    for relation_rules in rules["symmetric"].values():
        symmetric.extend(relation_rules.items())

    equivalence: list[tuple[str, str]] = []
    for relation_rules in rules["equivalence"].values():
        equivalence.extend(relation_rules.items())

    return rules, surface_to_predicate, composition, inverse, symmetric, equivalence


def predicate_graph(rules: dict) -> nx.DiGraph:
    graph = nx.DiGraph()
    for relation_rules in rules["compositional"].values():
        for left, right_map in relation_rules.items():
            for right, head in right_map.items():
                graph.add_edge(left, head)
                graph.add_edge(right, head)
    for family in ("inverse-equivalence", "symmetric"):
        for relation_rules in rules[family].values():
            for left, right in relation_rules.items():
                graph.add_edge(left, right)
    for relation_rules in rules["equivalence"].values():
        for left, right in relation_rules.items():
            graph.add_edge(left, right)
    return graph


def closure(
    base_facts: Iterable[Fact],
    composition: list[Rule],
    inverse: list[tuple[str, str]],
    symmetric: list[tuple[str, str]],
    equivalence: list[tuple[str, str]],
    blocked_ground_rule: GroundRule | None = None,
    allow_reflexive_composition: bool = False,
) -> tuple[set[Fact], dict[Fact, int]]:
    known = set(base_facts)
    first_round = {fact: 0 for fact in known}
    round_id = 0
    while True:
        round_id += 1
        new = set(known)
        by_source: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for source, predicate, target in known:
            by_source[source].append((predicate, target))
            for left, right in inverse:
                if predicate == left:
                    new.add((target, right, source))
            for left, right in symmetric:
                if predicate == left:
                    new.add((target, right, source))
            for left, right in equivalence:
                if predicate == left:
                    new.add((source, right, target))

        for source, left_predicate, middle in known:
            for right_predicate, target in by_source.get(middle, []):
                # Official RelationBuilder.compose_rel explicitly rejects a
                # composed edge whose endpoints are identical.  The opt-in
                # legacy mode exists only to reproduce and document the
                # earlier 628-case audit discrepancy.
                if source == target and not allow_reflexive_composition:
                    continue
                for wanted_left, wanted_right, head in composition:
                    if (left_predicate, right_predicate) != (wanted_left, wanted_right):
                        continue
                    grounded = (
                        (source, left_predicate, middle),
                        (middle, right_predicate, target),
                        (source, head, target),
                    )
                    if grounded != blocked_ground_rule:
                        new.add(grounded[2])

        delta = new - known
        if not delta:
            return known, first_round
        for fact in delta:
            first_round[fact] = round_id
        known = new


def recursive_internal_chain_depth(
    query: Fact,
    proof_steps: list[GroundRule],
    component_id: dict[str, int],
    recursive_component_ids: set[int],
) -> int:
    """Maximum recursive-predicate-internal step count on the released proof.

    This is a derivation diagnostic, not evidence that cycle topology itself is
    a counterfactual cause of the query.
    """

    proof_by_head: dict[Fact, tuple[Fact, Fact]] = {}
    for left, right, head in proof_steps:
        parents = (left, right)
        if head in proof_by_head and proof_by_head[head] != parents:
            raise ValueError(f"multiple released derivations for proof head: {head}")
        proof_by_head[head] = parents

    @lru_cache(maxsize=None)
    def visit(fact: Fact) -> int:
        if fact not in proof_by_head:
            return 0
        left, right = proof_by_head[fact]
        head_component = component_id.get(fact[1])
        is_feedback = head_component in recursive_component_ids and (
            component_id.get(left[1]) == head_component
            or component_id.get(right[1]) == head_component
        )
        return max(visit(left), visit(right)) + int(is_feedback)

    return visit(query)


def percentile(values: list[float], q: float):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def summarize_numbers(values: list[float]):
    return {
        "min": min(values) if values else None,
        "median": percentile(values, 0.5),
        "p90": percentile(values, 0.9),
        "max": max(values) if values else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.root.resolve()
    repo = root / "repo"
    paper_archive = root / "clutrr_paper_data.download"
    release_root = root / "paper_data" / "data_emnlp_final"
    rules, surface, composition, inverse, symmetric, equivalence = load_program(repo)

    pred_graph = predicate_graph(rules)
    components = list(nx.strongly_connected_components(pred_graph))
    component_id = {predicate: idx for idx, comp in enumerate(components) for predicate in comp}
    recursive_component_ids = {
        idx
        for idx, comp in enumerate(components)
        if len(comp) > 1 or any(pred_graph.has_edge(node, node) for node in comp)
    }

    counters = Counter()
    by_task: dict[str, Counter] = defaultdict(Counter)
    query_rounds: list[int] = []
    candidate_to_clean: list[float] = []
    minimum_source_covers: list[int] = []
    candidate_to_minimum_cover: list[float] = []
    grounded_deletion_tests = 0
    grounded_deletion_causal = 0
    schema_deletion_tests = 0
    schema_deletion_causal = 0
    instances_with_causal_ground_rule = 0
    instances_with_causal_rule_schema = 0
    instances_all_clean_sources_causal = 0
    clean_directed_entity_scc_instances = 0
    full_directed_entity_scc_instances = 0
    recommended_clean_bundle = "data_089907f8"
    recommended_total = 0
    recommended_feedback_chain_ge_2 = 0
    recommended_strict_ids: set[str] = set()
    recommended_legacy_strict_ids: set[str] = set()
    recommended_surface_f_combs: set[str] = set()
    recommended_canonical_sequences: set[tuple[str, ...]] = set()
    recommended_legacy_surface_f_combs: set[str] = set()
    recommended_legacy_canonical_sequences: set[tuple[str, ...]] = set()
    recommended_strict_by_k: Counter = Counter()
    recommended_legacy_strict_by_k: Counter = Counter()

    csv_files = sorted(glob.glob(str(release_root / "data_*" / "*_test.csv")))
    seen_ids: set[str] = set()
    for csv_name in csv_files:
        bundle = Path(csv_name).parent.name
        frame = pd.read_csv(csv_name)
        for _, row in frame.iterrows():
            instance_id = str(row["id"])
            if instance_id in seen_ids:
                raise ValueError(f"duplicate CLUTRR id: {instance_id}")
            seen_ids.add(instance_id)

            task = str(row["task_name"])
            task_family = task.split(".")[0].removeprefix("task_")
            is_recommended_clean = (
                bundle == recommended_clean_bundle and task_family == "1"
            )
            if is_recommended_clean:
                recommended_total += 1
            story_edges = ast.literal_eval(row["story_edges"])
            clean_types = ast.literal_eval(row["edge_types"])
            query_edge = ast.literal_eval(row["query_edge"])
            query = (query_edge[0], surface[str(row["target"])], query_edge[1])
            clean_edges = story_edges[: len(clean_types)]
            clean_facts = {
                (source, surface[predicate], target)
                for (source, target), predicate in zip(clean_edges, clean_types)
            }

            known, first_round = closure(
                clean_facts, composition, inverse, symmetric, equivalence
            )
            counters["instances"] += 1
            counters["exact_query_matches"] += int(query in known)
            if query not in known:
                raise AssertionError(f"query not recovered: {instance_id}")
            query_rounds.append(first_round[query])

            candidate_count = len(story_edges)
            clean_count = len(clean_types)
            ratio = candidate_count / clean_count
            candidate_to_clean.append(ratio)
            ctask = by_task[task_family]
            ctask["instances"] += 1
            ctask["candidate_edges"] += candidate_count
            ctask["clean_edges"] += clean_count

            clean_entity_graph = nx.DiGraph()
            clean_entity_graph.add_edges_from(clean_edges)
            clean_has_scc = any(
                len(comp) > 1
                for comp in nx.strongly_connected_components(clean_entity_graph)
            )
            clean_directed_entity_scc_instances += int(clean_has_scc)
            full_entity_graph = nx.DiGraph()
            full_entity_graph.add_edges_from(story_edges)
            full_has_scc = any(
                len(comp) > 1
                for comp in nx.strongly_connected_components(full_entity_graph)
            )
            full_directed_entity_scc_instances += int(full_has_scc)
            ctask["clean_entity_scc_instances"] += int(clean_has_scc)
            ctask["full_entity_scc_instances"] += int(full_has_scc)

            source_deletions = 0
            for fact in clean_facts:
                without, _ = closure(
                    clean_facts - {fact}, composition, inverse, symmetric, equivalence
                )
                source_deletions += int(query not in without)
            if source_deletions == len(clean_facts):
                instances_all_clean_sources_causal += 1
                minimum_cover = len(clean_facts)
            else:
                ordered_facts = sorted(clean_facts)
                minimum_cover = len(ordered_facts)
                for size in range(1, len(ordered_facts)):
                    found = False
                    for subset in itertools.combinations(ordered_facts, size):
                        subset_closure, _ = closure(
                            subset, composition, inverse, symmetric, equivalence
                        )
                        if query in subset_closure:
                            minimum_cover = size
                            found = True
                            break
                    if found:
                        break
            minimum_source_covers.append(minimum_cover)
            candidate_to_minimum_cover.append(candidate_count / minimum_cover)
            ctask["minimum_source_cover_sum"] += minimum_cover

            proof_steps = []
            # proof_state stores person names, whereas story_edges uses the
            # release's sorted integer IDs.  get_name_gender_string preserves
            # the same insertion order used to assign those sorted IDs.
            name_to_id = {
                item.rsplit(":", 1)[0]: idx
                for idx, item in enumerate(str(row["genders"]).split(","))
            }
            for layer in ast.literal_eval(row["proof_state"]):
                for head_surface, body_surfaces in layer.items():
                    head = (
                        name_to_id[head_surface[0]],
                        surface[head_surface[1]],
                        name_to_id[head_surface[2]],
                    )
                    left = (
                        name_to_id[body_surfaces[0][0]],
                        surface[body_surfaces[0][1]],
                        name_to_id[body_surfaces[0][2]],
                    )
                    right = (
                        name_to_id[body_surfaces[1][0]],
                        surface[body_surfaces[1][1]],
                        name_to_id[body_surfaces[1][2]],
                    )
                    proof_steps.append((left, right, head))

            internal_steps = 0
            causal_steps = 0
            legacy_reflexive_causal_steps = 0
            internal_schemas: set[Rule] = set()
            for ground_rule in proof_steps:
                left, right, head = ground_rule
                head_component = component_id.get(head[1])
                if head_component in recursive_component_ids and (
                    component_id.get(left[1]) == head_component
                    or component_id.get(right[1]) == head_component
                ):
                    internal_steps += 1
                    internal_schemas.add((left[1], right[1], head[1]))
                    grounded_deletion_tests += 1
                    without, _ = closure(
                        clean_facts,
                        composition,
                        inverse,
                        symmetric,
                        equivalence,
                        blocked_ground_rule=ground_rule,
                    )
                    if query not in without:
                        grounded_deletion_causal += 1
                        causal_steps += 1
                    if is_recommended_clean:
                        legacy_without, _ = closure(
                            clean_facts,
                            composition,
                            inverse,
                            symmetric,
                            equivalence,
                            blocked_ground_rule=ground_rule,
                            allow_reflexive_composition=True,
                        )
                        if query not in legacy_without:
                            legacy_reflexive_causal_steps += 1

            counters["proof_steps"] += len(proof_steps)
            counters["scc_internal_proof_steps"] += internal_steps
            counters["instances_with_scc_internal_step"] += int(internal_steps > 0)
            counters["instances_all_proof_steps_scc_internal"] += int(
                internal_steps == len(proof_steps)
            )
            if causal_steps:
                instances_with_causal_ground_rule += 1

            if is_recommended_clean:
                chain_depth = recursive_internal_chain_depth(
                    query,
                    proof_steps,
                    component_id,
                    recursive_component_ids,
                )
                has_feedback_chain = chain_depth >= 2
                recommended_feedback_chain_ge_2 += int(has_feedback_chain)
                canonical_sequence = tuple(surface[predicate] for predicate in clean_types)
                k = int(task.split(".", 1)[1])
                if has_feedback_chain and causal_steps:
                    recommended_strict_ids.add(instance_id)
                    recommended_surface_f_combs.add(str(row["f_comb"]))
                    recommended_canonical_sequences.add(canonical_sequence)
                    recommended_strict_by_k[k] += 1
                if has_feedback_chain and legacy_reflexive_causal_steps:
                    recommended_legacy_strict_ids.add(instance_id)
                    recommended_legacy_surface_f_combs.add(str(row["f_comb"]))
                    recommended_legacy_canonical_sequences.add(canonical_sequence)
                    recommended_legacy_strict_by_k[k] += 1

            causal_schemas = 0
            for schema in internal_schemas:
                schema_deletion_tests += 1
                without, _ = closure(
                    clean_facts,
                    [rule for rule in composition if rule != schema],
                    inverse,
                    symmetric,
                    equivalence,
                )
                if query not in without:
                    schema_deletion_causal += 1
                    causal_schemas += 1
            if causal_schemas:
                instances_with_causal_rule_schema += 1

    task_summary = {}
    for task_family, values in sorted(by_task.items()):
        task_summary[f"task_{task_family}"] = {
            **values,
            "candidate_to_clean_fact_ratio": values["candidate_edges"]
            / values["clean_edges"],
            "mean_minimum_source_cover": values["minimum_source_cover_sum"]
            / values["instances"],
            "paper_role": {
                "1": "clean",
                "2": "supporting-fact noise",
                "3": "irrelevant-fact noise",
                "4": "disconnected-fact noise",
            }.get(task_family, "other"),
        }

    official_only_ids = sorted(
        recommended_strict_ids - recommended_legacy_strict_ids
    )
    legacy_only_ids = sorted(
        recommended_legacy_strict_ids - recommended_strict_ids
    )
    recommended_clean_summary = {
        "bundle": recommended_clean_bundle,
        "role": "recommended clean diagnostic slice",
        "selection": (
            "released proof has >=2 recursive-predicate-internal composition "
            "steps and at least one such ground instance is query-deletion-causal"
        ),
        "interpretation_warning": (
            "This establishes recursive-chain participation and a causal ground "
            "instance, not that cycle topology itself is a counterfactual cause."
        ),
        "total_instances": recommended_total,
        "instances_with_feedback_chain_ge_2": recommended_feedback_chain_ge_2,
        "strict_instances": len(recommended_strict_ids),
        "strict_unique_surface_f_comb": len(recommended_surface_f_combs),
        "strict_unique_canonical_predicate_sequences": len(
            recommended_canonical_sequences
        ),
        "strict_instances_by_k": dict(sorted(recommended_strict_by_k.items())),
        "semantic_correction": {
            "official_semantics": (
                "RelationBuilder.compose_rel rejects composition when source == "
                "target; inverse-equivalence rules are applied only in their "
                "encoded direction"
            ),
            "legacy_reflexive_composition_semantics": {
                "strict_instances": len(recommended_legacy_strict_ids),
                "strict_unique_surface_f_comb": len(
                    recommended_legacy_surface_f_combs
                ),
                "strict_unique_canonical_predicate_sequences": len(
                    recommended_legacy_canonical_sequences
                ),
                "strict_instances_by_k": dict(
                    sorted(recommended_legacy_strict_by_k.items())
                ),
            },
            "official_only_affected_uuids": official_only_ids,
            "legacy_only_affected_uuids": legacy_only_ids,
        },
    }

    result = {
        "audit_scope": "official EMNLP-2019 paper test release",
        "artifact": {
            "official_archive_url": "https://drive.google.com/file/d/1SEq_e1IVCDDzsBIBhoUQ5pOVH5kxRoZF/view",
            "archive_bytes": paper_archive.stat().st_size,
            "archive_sha256": sha256(paper_archive),
            "repository_url": "https://github.com/facebookresearch/clutrr",
            "repository_commit": os.popen(
                f"git -C {repo} rev-parse HEAD"
            ).read().strip(),
            "license": "CC-BY-NC-4.0",
        },
        "predicate_graph": {
            "nodes": pred_graph.number_of_nodes(),
            "edges": pred_graph.number_of_edges(),
            "recursive_scc_count": len(recursive_component_ids),
            "recursive_sccs": sorted(
                [sorted(components[idx]) for idx in recursive_component_ids],
                key=lambda comp: (-len(comp), comp),
            ),
        },
        "test_release": {
            **counters,
            "unique_instances": len(seen_ids),
            "csv_files": len(csv_files),
            "query_rounds": summarize_numbers(query_rounds),
            "query_round_distribution": dict(sorted(Counter(query_rounds).items())),
            "candidate_to_clean_fact_ratio": summarize_numbers(candidate_to_clean),
            "minimum_source_cover": summarize_numbers(minimum_source_covers),
            "minimum_source_cover_distribution": dict(
                sorted(Counter(minimum_source_covers).items())
            ),
            "candidate_to_minimum_source_cover_ratio": summarize_numbers(
                candidate_to_minimum_cover
            ),
            "instances_all_clean_sources_deletion_causal": instances_all_clean_sources_causal,
            "grounded_scc_rule_deletion_tests": grounded_deletion_tests,
            "grounded_scc_rule_deletion_causal": grounded_deletion_causal,
            "instances_with_deletion_causal_grounded_scc_rule": instances_with_causal_ground_rule,
            "scc_rule_schema_deletion_tests": schema_deletion_tests,
            "scc_rule_schema_deletion_causal": schema_deletion_causal,
            "instances_with_deletion_causal_scc_rule_schema": instances_with_causal_rule_schema,
            "instances_with_clean_directed_entity_scc": clean_directed_entity_scc_instances,
            "instances_with_full_directed_entity_scc": full_directed_entity_scc_instances,
            "by_task_family": task_summary,
            "recommended_clean_slice": recommended_clean_summary,
        },
        "transposition_opportunity": {
            "instances_with_at_least_two_clean_sources": sum(
                1
                for csv_name in csv_files
                for _, row in pd.read_csv(csv_name).iterrows()
                if len(ast.literal_eval(row["edge_types"])) >= 2
            ),
            "depth_2_order_paths_per_subset": math.factorial(2),
            "depth_3_order_paths_per_subset": math.factorial(3),
            "interpretation": "Monotone source-set acquisition has exact cross-order transpositions, but the clean task has no source-selection choice and actual TT benefit remains an algorithmic result.",
        },
        "acl_eligibility": {
            "strengths": [
                "independent EMNLP benchmark family with AMT paraphrase templates",
                "canonical executable relation algebra and released proof_state",
                "all official test queries reproduced by an independent monotone closure",
                "query proofs repeatedly apply rules inside recursive predicate SCCs",
            ],
            "limitations": [
                "semi-synthetic family stories, not real documents",
                "global rules are known and are not latent natural-language source records",
                "all labels are entailed relation classes; no native Unknown/unseeded-cycle control",
                "the 846 entity-SCC cases occur only in clean task 1, which has no distractor candidates; released noisy tasks have no entity SCC",
                f"only {instances_with_causal_ground_rule:,}/{counters['instances']:,} instances have a deletion-causal grounded SCC proof step; {instances_with_causal_rule_schema:,} depend on at least one SCC rule schema",
                "clean task has candidate/clean-fact ratio 1; released noisy tasks provide only modest selection pressure",
                "released robust CSV omits gold relation labels for distractor edges and lacks exact text-record-to-fact alignment",
            ],
            "verdict": "Independent recursive-closure and language-transfer confirmation; not a second end-to-end confirmation of budgeted latent-rule acquisition or MCGS necessity.",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


if __name__ == "__main__":
    main()
