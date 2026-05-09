"""Analyze implicit reference chains across all extracted CUAD contracts.

Three graph variants are compared:
  1. Explicit-only: REFERENCES + IS_PART_OF edges between CLAUSE nodes
  2. +Strong Implicit: Add edges via shared DEFINED_TERMs (A DEFINES term, B USES term => B->A)
  3. +Full Implicit: Also add edges via PARTY co-mention and term co-usage

Usage:
    python scripts/analyze_implicit_refs.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import networkx as nx

FULLGRAPH_DIR = Path("data/cuad/grpo_lex_replicated/fullgraphs")


def load_fullgraph(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_clause_only_graph(fg: dict) -> tuple[set[str], nx.DiGraph]:
    """Build a graph with only CLAUSE nodes."""
    clause_ids = {
        n["id"] for n in fg["nodes"] if n.get("node_type") == "CLAUSE"
    }
    G = nx.DiGraph()
    G.add_nodes_from(clause_ids)
    return clause_ids, G


def add_explicit_edges(G: nx.DiGraph, fg: dict, clause_ids: set[str]):
    """Add REFERENCES and IS_PART_OF edges between CLAUSE nodes."""
    for e in fg["edges"]:
        if e["type"] in ("REFERENCES", "IS_PART_OF"):
            if e["src"] in clause_ids and e["tgt"] in clause_ids and e["src"] != e["tgt"]:
                G.add_edge(e["src"], e["tgt"])


def add_strong_implicit(G: nx.DiGraph, fg: dict, clause_ids: set[str]):
    """A DEFINES term X, B USES term X => B depends on A."""
    term_to_definer: dict[str, set[str]] = defaultdict(set)
    term_to_users: dict[str, set[str]] = defaultdict(set)

    for e in fg["edges"]:
        if e["type"] == "DEFINES" and e["src"] in clause_ids:
            term_to_definer[e["tgt"]].add(e["src"])
        if e["type"] == "USES" and e["src"] in clause_ids:
            term_to_users[e["tgt"]].add(e["src"])

    implicit_count = 0
    for term, definers in term_to_definer.items():
        users = term_to_users.get(term, set())
        for user_clause in users:
            for definer_clause in definers:
                if user_clause != definer_clause:
                    if not G.has_edge(user_clause, definer_clause):
                        G.add_edge(user_clause, definer_clause)
                        implicit_count += 1
    return implicit_count


def add_medium_implicit(G: nx.DiGraph, fg: dict, clause_ids: set[str]):
    """Selective term co-usage with calibrated connectivity.

    - Terms used by exactly 2 clauses: bidirectional (tight coupling)
    - Terms used by 3-7 clauses: unidirectional (later → earliest)
    - High-frequency 'stop terms' are filtered out
    """
    term_to_clauses: dict[str, set[str]] = defaultdict(set)

    stop_terms = {
        "term:agreement", "term:party", "term:parties",
        "term:company", "term:effective date", "term:section",
        "term:affiliate", "term:affiliates", "term:license",
    }

    term_definers: dict[str, set[str]] = defaultdict(set)
    for e in fg["edges"]:
        if e["type"] == "DEFINES" and e["src"] in clause_ids:
            term_id = e["tgt"]
            if term_id.startswith("term:"):
                canonical = term_id.lower().strip()
                term_definers[canonical].add(e["src"])

    for e in fg["edges"]:
        if e["type"] in ("USES", "DEFINES") and e["src"] in clause_ids:
            term_id = e["tgt"]
            if term_id.startswith("term:"):
                canonical = term_id.lower().strip()
                if canonical not in stop_terms:
                    term_to_clauses[canonical].add(e["src"])

    implicit_count = 0
    for term, clauses in term_to_clauses.items():
        if len(clauses) < 2 or len(clauses) > 5:
            continue

        definers = term_definers.get(term, set())
        clause_list = sorted(clauses)

        if definers:
            definer = sorted(definers)[0]
            for c in clause_list:
                if c != definer:
                    if not G.has_edge(c, definer):
                        G.add_edge(c, definer)
                        implicit_count += 1
                    if len(clauses) == 2 and not G.has_edge(definer, c):
                        G.add_edge(definer, c)
                        implicit_count += 1
        else:
            anchor = clause_list[0]
            for i in range(1, len(clause_list)):
                if not G.has_edge(clause_list[i], anchor):
                    G.add_edge(clause_list[i], anchor)
                    implicit_count += 1

    return implicit_count


def add_full_implicit(G: nx.DiGraph, fg: dict, clause_ids: set[str]):
    """Add edges via shared term co-usage and party co-mention."""
    term_to_clauses: dict[str, set[str]] = defaultdict(set)
    party_to_clauses: dict[str, set[str]] = defaultdict(set)

    for e in fg["edges"]:
        if e["type"] in ("USES", "DEFINES") and e["src"] in clause_ids:
            term_id = e["tgt"]
            if term_id.startswith("term:"):
                canonical = term_id.lower().strip()
                term_to_clauses[canonical].add(e["src"])
        if e["type"] in ("MENTIONS_PARTY",) and e["src"] in clause_ids:
            party_to_clauses[e["tgt"]].add(e["src"])

    implicit_count = 0

    high_freq_threshold = max(3, len(clause_ids) * 0.3)

    for term, clauses in term_to_clauses.items():
        if len(clauses) < 2 or len(clauses) > high_freq_threshold:
            continue
        clause_list = sorted(clauses)
        for i in range(len(clause_list)):
            for j in range(i + 1, len(clause_list)):
                a, b = clause_list[i], clause_list[j]
                if not G.has_edge(a, b):
                    G.add_edge(a, b)
                    implicit_count += 1
                if not G.has_edge(b, a):
                    G.add_edge(b, a)
                    implicit_count += 1

    return implicit_count


def scc_stats(G: nx.DiGraph, clause_ids: set[str]) -> dict:
    sccs = [s for s in nx.strongly_connected_components(G) if len(s) > 1]
    scc_nodes = set()
    for s in sccs:
        scc_nodes.update(s)
    n = len(clause_ids)
    return {
        "scc_count": len(sccs),
        "scc_node_count": len(scc_nodes),
        "scc_node_ratio": round(len(scc_nodes) / n * 100, 2) if n else 0,
        "largest_scc": max((len(s) for s in sccs), default=0),
        "total_edges": G.number_of_edges(),
        "total_clauses": n,
    }


def main():
    fg_files = sorted(FULLGRAPH_DIR.glob("*_fullgraph.json"))
    if not fg_files:
        print("No fullgraph files found.")
        sys.exit(1)

    print(f"{'Contract':<55} | {'Clauses':>7} | {'Mode':<18} | {'Edges':>5} | {'SCCs':>4} | {'SCC_Nodes':>9} | {'SCC%':>6} | {'Largest':>7}")
    print("-" * 130)

    agg = {"explicit": [], "strong": [], "medium": [], "full": []}

    for fg_file in fg_files:
        fg = load_fullgraph(fg_file)
        contract_id = fg.get("contract_id", fg_file.stem)
        short_name = contract_id[:53]

        clause_ids, G1 = build_clause_only_graph(fg)
        add_explicit_edges(G1, fg, clause_ids)
        s1 = scc_stats(G1, clause_ids)
        agg["explicit"].append(s1)

        _, G2 = build_clause_only_graph(fg)
        add_explicit_edges(G2, fg, clause_ids)
        add_strong_implicit(G2, fg, clause_ids)
        s2 = scc_stats(G2, clause_ids)
        agg["strong"].append(s2)

        _, G_med = build_clause_only_graph(fg)
        add_explicit_edges(G_med, fg, clause_ids)
        add_strong_implicit(G_med, fg, clause_ids)
        add_medium_implicit(G_med, fg, clause_ids)
        s_med = scc_stats(G_med, clause_ids)
        agg["medium"].append(s_med)

        _, G3 = build_clause_only_graph(fg)
        add_explicit_edges(G3, fg, clause_ids)
        add_strong_implicit(G3, fg, clause_ids)
        add_full_implicit(G3, fg, clause_ids)
        s3 = scc_stats(G3, clause_ids)
        agg["full"].append(s3)

        for mode, s in [("Explicit", s1), ("+Strong", s2), ("+Medium", s_med), ("+Full", s3)]:
            marker = " ***" if 2.0 <= s["scc_node_ratio"] <= 15.0 else (" !!!" if s["scc_node_ratio"] > 15.0 else "")
            print(
                f"{short_name:<55} | {s['total_clauses']:>7} | {mode:<18} | "
                f"{s['total_edges']:>5} | {s['scc_count']:>4} | {s['scc_node_count']:>9} | "
                f"{s['scc_node_ratio']:>5.1f}% | {s['largest_scc']:>7}{marker}"
            )
        print()

    print("=" * 130)
    print("AGGREGATE SUMMARY")
    print("=" * 130)
    total_clauses = sum(s["total_clauses"] for s in agg["explicit"])
    for mode_name, mode_data in agg.items():
        total_scc_nodes = sum(s["scc_node_count"] for s in mode_data)
        total_sccs = sum(s["scc_count"] for s in mode_data)
        contracts_with_scc = sum(1 for s in mode_data if s["scc_count"] > 0)
        largest = max(s["largest_scc"] for s in mode_data)
        ratio = round(total_scc_nodes / total_clauses * 100, 2) if total_clauses else 0
        marker = " <-- target zone" if 3 <= ratio <= 10 else ""
        print(
            f"  {mode_name:<20}: {contracts_with_scc:>2}/{len(mode_data)} contracts with SCC | "
            f"total_SCCs={total_sccs:>3} | SCC_nodes={total_scc_nodes:>4}/{total_clauses} ({ratio}%) | "
            f"largest_SCC={largest}{marker}"
        )

    print(f"\n  BGB reference: ~5% of nodes in SCCs")


if __name__ == "__main__":
    main()
