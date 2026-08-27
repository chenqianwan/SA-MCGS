#!/usr/bin/env python3
"""Recompute native-label and current SA-MCGS graph statistics.

This script intentionally keeps two kinds of evidence separate:

1. native dataset annotations (what the dataset actually labels), and
2. graph/SCC statistics produced by the repository's current loaders.

Run from the repository root with a Python environment containing the
project dependencies, for example:

    python 2026NAACL/dataset_audit/audit_existing_sa_datasets.py
"""

from __future__ import annotations

import json
import gzip
import statistics
import sys
from collections import Counter
from pathlib import Path

import networkx as nx


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.data.contractnli_loader import ContractNLILoader  # noqa: E402
from src.data.cuad_loader import CUADLoader  # noqa: E402
from src.data.loader import QuantLawLoader  # noqa: E402


def graph_scc_summary(graphs: list[tuple[str, object]]) -> dict:
    """Summarize non-singleton SCCs in repository DependencyGraph objects."""
    total_nodes = 0
    total_edges = 0
    scc_sizes: list[int] = []
    graphs_with_scc = 0

    for graph_id, graph in graphs:
        nx_graph = nx.DiGraph()
        nx_graph.add_nodes_from(graph.clauses)
        nx_graph.add_edges_from(
            (edge.source, edge.target)
            for edge in graph.edges
            if edge.source in graph.clauses and edge.target in graph.clauses
        )
        sizes = [
            len(component)
            for component in nx.strongly_connected_components(nx_graph)
            if len(component) > 1
        ]
        if sizes:
            graphs_with_scc += 1
            scc_sizes.extend(sizes)
        total_nodes += nx_graph.number_of_nodes()
        total_edges += nx_graph.number_of_edges()

    return {
        "graphs": len(graphs),
        "nodes": total_nodes,
        "edges": total_edges,
        "graphs_with_nontrivial_scc": graphs_with_scc,
        "nontrivial_sccs": len(scc_sizes),
        "nodes_in_nontrivial_sccs": sum(scc_sizes),
        "max_scc_size": max(scc_sizes, default=0),
        "median_scc_size": statistics.median(scc_sizes) if scc_sizes else 0,
    }


def audit_contractnli() -> dict:
    data_dir = ROOT / "data/contractnli/contract-nli"
    native = {
        "documents": 0,
        "hypotheses": set(),
        "annotations": 0,
        "raw_text_spans": 0,
        "evidence_span_references": 0,
        "choices": Counter(),
        "document_char_lengths": [],
        "split_documents": {},
    }
    loader = ContractNLILoader(str(data_dir))
    graphs = []

    for split in ("train", "dev", "test"):
        path = data_dir / f"{split}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        documents = data["documents"]
        native["split_documents"][split] = len(documents)
        native["documents"] += len(documents)
        native["hypotheses"].update(data["labels"])
        for document in documents:
            native["document_char_lengths"].append(len(document["text"]))
            native["raw_text_spans"] += len(document["spans"])
            annotations = document["annotation_sets"][0]["annotations"]
            native["annotations"] += len(annotations)
            for annotation in annotations.values():
                native["choices"][annotation["choice"]] += 1
                native["evidence_span_references"] += len(annotation["spans"])
        graphs.extend((graph_id, graph) for graph_id, graph, _ in loader.load(split))

    result = {
        "native": {
            "documents": native["documents"],
            "hypotheses": len(native["hypotheses"]),
            "document_hypothesis_annotations": native["annotations"],
            "raw_text_spans": native["raw_text_spans"],
            "evidence_span_references": native["evidence_span_references"],
            "choices": dict(native["choices"]),
            "median_document_chars": statistics.median(native["document_char_lengths"]),
            "mean_document_chars": round(
                statistics.mean(native["document_char_lengths"]), 1
            ),
            "split_documents": native["split_documents"],
        },
        "current_sa_loader": graph_scc_summary(graphs),
    }
    return result


def audit_cuad() -> dict:
    data_dir = ROOT / "data/cuad"
    json_path = data_dir / "CUAD_v1/CUAD_v1/CUAD_v1.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    entries = data["data"]
    paragraphs = [paragraph for entry in entries for paragraph in entry["paragraphs"]]
    qas = [qa for paragraph in paragraphs for qa in paragraph["qas"]]
    txt_dir = data_dir / "CUAD_v1/CUAD_v1/full_contract_txt"
    text_sizes = [path.stat().st_size for path in txt_dir.glob("*.txt")]

    native = {
        "documents": len(entries),
        "paragraphs": len(paragraphs),
        "qas": len(qas),
        "answer_spans": sum(len(qa["answers"]) for qa in qas),
        "impossible_qas": sum(bool(qa.get("is_impossible")) for qa in qas),
        "categories": len({qa["question"] for qa in qas}),
        "full_text_files": len(text_sizes),
        "full_text_total_bytes": sum(text_sizes),
        "median_full_text_bytes": statistics.median(text_sizes),
    }

    graphs = CUADLoader(str(data_dir)).load()
    return {
        "native": native,
        "current_sa_loader": graph_scc_summary(graphs),
    }


def audit_quantlaw() -> dict:
    graphs = QuantLawLoader(str(ROOT / "data/quantlaw")).load()
    return {
        "downloaded_graph_ids": [graph_id for graph_id, _ in graphs],
        "current_sa_loader": graph_scc_summary(graphs),
        "per_graph": {
            graph_id: {
                "nodes": len(graph.clauses),
                "edges": len(graph.edges),
            }
            for graph_id, graph in graphs
        },
    }


def _debian_package_names(path: Path) -> set[str]:
    names: set[str] = set()
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("Package: "):
                names.add(line.removeprefix("Package: ").strip())
    return names


def audit_debian_sa_snapshot() -> dict:
    data_dir = ROOT / "experiments/cross_domain/20241027.cards.debian_pkgs"
    deps_path = data_dir / "20241027.debian_pkgs.deps.gz"
    packages_path = data_dir / "20241027.debian_pkgs.packages.txt.gz"
    available = _debian_package_names(packages_path)
    all_dependency_nodes: set[str] = set()
    raw_pairs: list[tuple[str, str]] = []
    raw_edges = 0
    with gzip.open(deps_path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            tokens = line.split()
            if len(tokens) < 2:
                continue
            package, dependencies = tokens[0], tokens[1:]
            all_dependency_nodes.add(package)
            all_dependency_nodes.update(dependencies)
            for dependency in dependencies:
                if dependency == package:
                    continue
                raw_edges += 1
                raw_pairs.append((package, dependency))
    valid_nodes = available & all_dependency_nodes
    valid_pairs = [
        (package, dependency)
        for package, dependency in raw_pairs
        if package in valid_nodes and dependency in valid_nodes
    ]
    graph = nx.DiGraph()
    graph.add_nodes_from(valid_nodes)
    graph.add_edges_from(valid_pairs)
    sizes = sorted(
        (
            len(component)
            for component in nx.strongly_connected_components(graph)
            if len(component) > 1
        ),
        reverse=True,
    )
    return {
        "snapshot": "2024-10-27",
        "all_unique_package_records": len(available),
        "current_loader_nodes": len(valid_nodes),
        "raw_dependency_edges": raw_edges,
        "current_loader_edge_records": len(valid_pairs),
        "unique_valid_dependency_edges": graph.number_of_edges(),
        "skipped_edges_with_missing_record": raw_edges - len(valid_pairs),
        "nontrivial_sccs": len(sizes),
        "nodes_in_nontrivial_sccs": sum(sizes),
        "max_scc_size": max(sizes, default=0),
        "largest_scc_sizes": sizes[:12],
    }


def main() -> None:
    output = {
        "scope_note": (
            "Native annotations and loader-derived SCC statistics are different "
            "evidence and must not be conflated."
        ),
        "contractnli": audit_contractnli(),
        "cuad": audit_cuad(),
        "quantlaw_local_subset": audit_quantlaw(),
        "debian_existing_sa_snapshot": audit_debian_sa_snapshot(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
