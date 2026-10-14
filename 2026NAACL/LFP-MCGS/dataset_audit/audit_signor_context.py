#!/usr/bin/env python3
"""Measure how SIGNOR SCCs survive biologically meaningful context filters.

The unfiltered SIGNOR interaction graph aggregates species, cell types, tissues,
and direct/indirect observations.  Such an aggregate SCC is not automatically a
coherent causal reasoning instance.  This audit reports both the tempting raw
topology and the context-frozen topology needed for an honest NLP benchmark.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx


def entity_key(row: dict[str, str], side: str) -> tuple[str, str]:
    identifier = row[f"ID{side}"].strip()
    if identifier:
        return row[f"DATABASE{side}"].strip(), identifier
    return "NAME", row[f"ENTITY{side}"].strip()


def load_signed(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            effect = row["EFFECT"].strip('"')
            if effect.startswith("up-regulates"):
                sign = "+"
            elif effect.startswith("down-regulates"):
                sign = "-"
            else:
                continue
            row["sign"] = sign
            row["source"] = entity_key(row, "A")
            row["target"] = entity_key(row, "B")
            rows.append(row)
    return rows


def graph_stats(
    rows: list[dict], *, group_context: bool, require_nonempty_context: bool
) -> dict:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        cell = row["CELL_DATA"].strip()
        tissue = row["TISSUE_DATA"].strip()
        if require_nonempty_context and not (cell or tissue):
            continue
        key = (
            row["TAX_ID"].strip(),
            cell,
            tissue,
            row["DIRECT"].strip(),
        ) if group_context else ("ALL",)
        groups[key].append(row)

    component_sizes = []
    cyclic_nodes = set()
    rows_inside_scc = 0
    opposite_pairs = 0
    groups_with_scc = 0
    for group_key, group_rows in groups.items():
        graph = nx.DiGraph()
        graph.add_edges_from((row["source"], row["target"]) for row in group_rows)
        components = [
            component
            for component in nx.strongly_connected_components(graph)
            if len(component) > 1
        ]
        if components:
            groups_with_scc += 1
        component_of = {
            node: component_id
            for component_id, component in enumerate(components)
            for node in component
        }
        component_sizes.extend(len(component) for component in components)
        cyclic_nodes.update((group_key, node) for node in component_of)
        rows_inside_scc += sum(
            1
            for row in group_rows
            if row["source"] in component_of
            and row["target"] in component_of
            and component_of[row["source"]] == component_of[row["target"]]
        )
        signs_by_pair: dict[tuple, set[str]] = defaultdict(set)
        for row in group_rows:
            signs_by_pair[(row["source"], row["target"])].add(row["sign"])
        opposite_pairs += sum(signs == {"+", "-"} for signs in signs_by_pair.values())

    return {
        "records": sum(len(group_rows) for group_rows in groups.values()),
        "context_groups": len(groups),
        "groups_with_nontrivial_scc": groups_with_scc,
        "nontrivial_sccs": len(component_sizes),
        "largest_scc": max(component_sizes, default=0),
        "cyclic_nodes": len(cyclic_nodes),
        "records_inside_scc": rows_inside_scc,
        "opposite_sign_pairs": opposite_pairs,
        "largest_sccs": sorted(component_sizes, reverse=True)[:10],
    }


def evidence_stats(rows: list[dict]) -> dict:
    sentences = Counter(
        row["SENTENCE"].strip().strip('"')
        for row in rows
        if row["SENTENCE"].strip().strip('"')
    )
    pmids = Counter(row["PMID"].strip() for row in rows if row["PMID"].strip())
    mention_counts = Counter()
    for row in rows:
        sentence = row["SENTENCE"].casefold()
        entity_a = row["ENTITYA"].strip('"').casefold()
        entity_b = row["ENTITYB"].strip('"').casefold()
        mentions = int(bool(entity_a and entity_a in sentence)) + int(
            bool(entity_b and entity_b in sentence)
        )
        mention_counts[str(mentions)] += 1
    return {
        "unique_evidence_sentences": len(sentences),
        "sentence_edges_median": statistics.median(sentences.values()) if sentences else 0,
        "sentence_edges_max": max(sentences.values(), default=0),
        "sentences_reused_ge_2": sum(count >= 2 for count in sentences.values()),
        "sentences_reused_ge_5": sum(count >= 5 for count in sentences.values()),
        "unique_pmids": len(pmids),
        "pmid_edges_median": statistics.median(pmids.values()) if pmids else 0,
        "pmid_edges_max": max(pmids.values(), default=0),
        "surface_entity_mentions_per_record": dict(mention_counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    signed = load_signed(args.input)
    human = [row for row in signed if row["TAX_ID"].strip() == "9606"]
    human_direct = [row for row in human if row["DIRECT"].strip() == "t"]

    result = {
        "input": str(args.input),
        "signed_records": len(signed),
        "context_coverage": {
            "cell_nonempty": sum(bool(row["CELL_DATA"].strip()) for row in signed),
            "tissue_nonempty": sum(bool(row["TISSUE_DATA"].strip()) for row in signed),
            "either_cell_or_tissue_nonempty": sum(
                bool(row["CELL_DATA"].strip() or row["TISSUE_DATA"].strip())
                for row in signed
            ),
        },
        "profiles": {},
        "evidence": evidence_stats(signed),
    }
    for name, rows in {
        "all_signed": signed,
        "human": human,
        "human_direct": human_direct,
    }.items():
        result["profiles"][name] = {
            "unstratified": graph_stats(
                rows, group_context=False, require_nonempty_context=False
            ),
            "exact_context_including_blank": graph_stats(
                rows, group_context=True, require_nonempty_context=False
            ),
            "exact_nonempty_context": graph_stats(
                rows, group_context=True, require_nonempty_context=True
            ),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
