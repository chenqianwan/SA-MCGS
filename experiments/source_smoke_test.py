"""Smoke test: 5 source-localization methods on ablation data.

Methods:
  M1* Forward Reachability  — how many new-OC nodes reachable via DIRECTED edges?
  M2* Reverse Propagation   — from each new-OC node, walk BACKWARDS; who is visited most?
  M3  NSDLib NETSLEUTH       — classic MDL-based source detection (Prakash+ 2012)
  M4  NSDLib Rumor Centrality — Shah & Zaman on the infected subgraph
  M5  Composite Score        — weighted blend of topology + Δμ + OC change

Key fix from previous attempt: USE DIRECTED EDGES for M1*/M2*.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque, Counter
from pathlib import Path

import networkx as nx
import yaml
from loguru import logger

# NSDLib
try:
    import nsdlib as nsd
    from nsdlib import NodeEvaluationAlgorithm
    HAS_NSDLIB = True
except ImportError:
    HAS_NSDLIB = False

from src.data.loader import QuantLawLoader
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner


def load_graph(config):
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz"
    )
    DomainGraphPruner(config).prune(graph)
    return TarjanSCCDetector().detect(graph)


def build_nx_graphs(graph, scc_ids: set[str]):
    """Build both directed and undirected NetworkX graphs for the SCC."""
    G_dir = nx.DiGraph()
    G_undir = nx.Graph()
    G_dir.add_nodes_from(scc_ids)
    G_undir.add_nodes_from(scc_ids)
    for e in graph.edges:
        if e.source in scc_ids and e.target in scc_ids:
            G_dir.add_edge(e.source, e.target)
            G_undir.add_edge(e.source, e.target)
    return G_dir, G_undir


# ── M1*: Forward Reachability (DIRECTED) ────────────────────────────

def m1_forward_reachability(G_dir: nx.DiGraph, all_ids: set, new_oc: set):
    """For each node, count how many new-OC nodes are reachable via directed paths.
    Weight by inverse distance. The source should be UPSTREAM of victims."""
    scores = {}
    for node in all_ids:
        lengths = nx.single_source_shortest_path_length(G_dir, node)
        reach_score = 0
        reach_count = 0
        for oc_node in new_oc:
            if oc_node in lengths and lengths[oc_node] > 0:
                reach_count += 1
                reach_score += 1.0 / lengths[oc_node]
        scores[node] = (reach_count, reach_score)
    ranked = sorted(scores.items(), key=lambda x: (-x[1][0], -x[1][1]))
    return [(cid, cnt, sc) for cid, (cnt, sc) in ranked]


# ── M2*: Reverse Propagation (DIRECTED, walk backwards) ─────────────

def m2_reverse_propagation(G_dir: nx.DiGraph, all_ids: set, new_oc: set):
    """From each new-OC node, walk BACKWARDS along directed edges.
    Count how often each node is visited. The true source should be
    a common upstream ancestor of many victims."""
    G_rev = G_dir.reverse()
    visit_count = Counter()
    visit_weight = Counter()

    for oc_node in new_oc:
        lengths = nx.single_source_shortest_path_length(G_rev, oc_node)
        for ancestor, dist in lengths.items():
            if dist > 0:
                visit_count[ancestor] += 1
                visit_weight[ancestor] += 1.0 / dist

    ranked = sorted(all_ids, key=lambda x: (-visit_count[x], -visit_weight[x]))
    return [(cid, visit_count[cid], visit_weight[cid]) for cid in ranked]


# ── M3: NSDLib NETSLEUTH ────────────────────────────────────────────

def m3_netsleuth(G_undir: nx.Graph, new_oc: set):
    """Run NETSLEUTH on the infected subgraph."""
    if not HAS_NSDLIB or not new_oc:
        return []
    try:
        IG = G_undir.subgraph(new_oc).copy()
        if len(IG.nodes) == 0:
            return []
        result = nsd.source_detection(IG, NodeEvaluationAlgorithm.NET_SLEUTH)
        ranked = sorted(result.nodes_data.items(), key=lambda x: -x[1])
        return [(cid, sc) for cid, sc in ranked]
    except Exception as e:
        logger.warning(f"NETSLEUTH failed: {e}")
        return []


# ── M4: NSDLib Centrality ───────────────────────────────────────────

def m4_centrality(G_undir: nx.Graph, all_ids: set, new_oc: set):
    """Run various centrality-based detection on the FULL SCC graph,
    but only consider the infected subgraph for scoring."""
    if not HAS_NSDLIB or not new_oc:
        return []
    try:
        IG = G_undir.subgraph(new_oc).copy()
        if len(IG.nodes) == 0:
            return []
        result = nsd.source_detection(IG, NodeEvaluationAlgorithm.CENTRALITY_CLOSENESS)
        ranked = sorted(result.nodes_data.items(), key=lambda x: -x[1])
        return [(cid, sc) for cid, sc in ranked]
    except Exception as e:
        logger.warning(f"Centrality failed: {e}")
        return []


# ── M5: Composite Score ─────────────────────────────────────────────

def m5_composite(G_dir, all_ids, new_oc, delta_scores):
    """Combine:
      - Forward reachability (topology)  weight=0.4
      - Reverse propagation (topology)   weight=0.3
      - Delta μ rank (statistical)       weight=0.3
    """
    m1 = m1_forward_reachability(G_dir, all_ids, new_oc)
    m2 = m2_reverse_propagation(G_dir, all_ids, new_oc)

    def normalize_ranks(ranked_list):
        n = len(ranked_list)
        return {item[0]: 1.0 - i / n for i, item in enumerate(ranked_list)}

    m1_norm = normalize_ranks(m1)
    m2_norm = normalize_ranks(m2)

    delta_ranked = sorted(delta_scores.items(), key=lambda x: -x[1])
    delta_norm = normalize_ranks([(k, v) for k, v in delta_ranked])

    composite = {}
    for cid in all_ids:
        composite[cid] = (
            0.4 * m1_norm.get(cid, 0)
            + 0.3 * m2_norm.get(cid, 0)
            + 0.3 * delta_norm.get(cid, 0)
        )
    ranked = sorted(composite.items(), key=lambda x: -x[1])
    return [(cid, sc) for cid, sc in ranked]


# ── Main ────────────────────────────────────────────────────────────

def get_rank(ranked_list, target):
    for i, item in enumerate(ranked_list):
        if item[0] == target:
            return i + 1
    return len(ranked_list)


def main():
    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    graph = load_graph(config)

    with open("experiments/results/ablation_suite.json") as f:
        ablation = json.load(f)

    all_cases = []
    for key in ["exp1_cross_scale", "exp2_multi_target", "exp3_repeated"]:
        all_cases.extend(ablation.get(key, []))

    print("=" * 130)
    print("SOURCE LOCALIZATION SMOKE TEST — 5 Methods")
    print("  M1*: Forward Reachability (DIRECTED)")
    print("  M2*: Reverse Propagation (DIRECTED, backwards)")
    print("  M3:  NSDLib NETSLEUTH")
    print("  M4:  NSDLib Closeness Centrality")
    print("  M5:  Composite (M1* + M2* + Δμ)")
    print("=" * 130)

    header = (f"{'Label':<30} | {'Tgt':<12} | {'#OC':>3} | "
              f"{'M1* FwdR':>9} {'Top1':<10} | "
              f"{'M2* RevP':>9} {'Top1':<10} | "
              f"{'M3 NETS':>8} {'Top1':<10} | "
              f"{'M4 Centr':>9} {'Top1':<10} | "
              f"{'M5 Comp':>8} {'Top1':<10}")
    print(f"\n{header}")
    print("-" * 130)

    hits = {f"m{i}": 0 for i in range(1, 6)}
    top3 = {f"m{i}": 0 for i in range(1, 6)}
    top5 = {f"m{i}": 0 for i in range(1, 6)}
    total_valid = 0

    details = []

    for case in all_cases:
        target = case["target_id"]
        scc_ids = set(case["scc_clause_ids"])
        label = case["label"]
        new_oc = set(case["pert_mcgs"]["oc_detected_clauses"]) - set(case["clean_mcgs"]["oc_detected_clauses"])

        if not new_oc:
            print(f"{label:<30} | {target:<12} | {'—':>3} | (no new OC — skipped)")
            continue

        total_valid += 1
        G_dir, G_undir = build_nx_graphs(graph, scc_ids)

        clean_d = case["clean_mcgs"]["clause_details"]
        pert_d = case["pert_mcgs"]["clause_details"]
        delta_scores = {
            cid: pert_d.get(cid, {}).get("mean_score", 0) - clean_d.get(cid, {}).get("mean_score", 0)
            for cid in scc_ids
        }

        r1 = m1_forward_reachability(G_dir, scc_ids, new_oc)
        r2 = m2_reverse_propagation(G_dir, scc_ids, new_oc)
        r3 = m3_netsleuth(G_undir, new_oc)
        r4 = m4_centrality(G_undir, scc_ids, new_oc)
        r5 = m5_composite(G_dir, scc_ids, new_oc, delta_scores)

        ranks = {
            "m1": get_rank(r1, target),
            "m2": get_rank(r2, target),
            "m3": get_rank(r3, target) if r3 else None,
            "m4": get_rank(r4, target) if r4 else None,
            "m5": get_rank(r5, target),
        }

        for mk in ranks:
            r = ranks[mk]
            if r is not None:
                if r == 1: hits[mk] += 1
                if r <= 3: top3[mk] += 1
                if r <= 5: top5[mk] += 1

        def fmt_rank(r, n):
            if r is None: return "—"
            return f"#{r}/{n}" if r > 1 else "✅"

        n = len(scc_ids)
        t1 = lambda lst: lst[0][0] if lst else "—"
        print(f"{label:<30} | {target:<12} | {len(new_oc):>3} | "
              f"{fmt_rank(ranks['m1'], n):>9} {t1(r1):<10} | "
              f"{fmt_rank(ranks['m2'], n):>9} {t1(r2):<10} | "
              f"{fmt_rank(ranks['m3'], len(new_oc) if r3 else n):>8} {t1(r3):<10} | "
              f"{fmt_rank(ranks['m4'], len(new_oc) if r4 else n):>9} {t1(r4):<10} | "
              f"{fmt_rank(ranks['m5'], n):>8} {t1(r5):<10}")

        details.append({
            "label": label, "target": target, "scc_size": n,
            "new_oc": sorted(new_oc), "new_oc_count": len(new_oc),
            "m1_rank": ranks["m1"], "m1_top5": [x[0] for x in r1[:5]],
            "m2_rank": ranks["m2"], "m2_top5": [x[0] for x in r2[:5]],
            "m3_rank": ranks["m3"], "m3_top5": [x[0] for x in r3[:5]] if r3 else [],
            "m4_rank": ranks["m4"], "m4_top5": [x[0] for x in r4[:5]] if r4 else [],
            "m5_rank": ranks["m5"], "m5_top5": [x[0] for x in r5[:5]],
        })

    print("-" * 130)
    print(f"\n{'Method':<35} | {'Top-1':>8} | {'Top-3':>8} | {'Top-5':>8} | {'N':>3}")
    print("-" * 70)
    labels = {
        "m1": "M1* Forward Reachability (directed)",
        "m2": "M2* Reverse Propagation (directed)",
        "m3": "M3  NSDLib NETSLEUTH",
        "m4": "M4  NSDLib Closeness Centrality",
        "m5": "M5  Composite (topo + stat)",
    }
    for mk in ["m1", "m2", "m3", "m4", "m5"]:
        h = hits[mk]; t3 = top3[mk]; t5 = top5[mk]
        pct1 = f"{h}/{total_valid} ({h/total_valid:.0%})" if total_valid else "—"
        pct3 = f"{t3}/{total_valid} ({t3/total_valid:.0%})" if total_valid else "—"
        pct5 = f"{t5}/{total_valid} ({t5/total_valid:.0%})" if total_valid else "—"
        print(f"{labels[mk]:<35} | {pct1:>8} | {pct3:>8} | {pct5:>8} | {total_valid:>3}")

    # Per-case detail
    for d in details:
        print(f"\n{'─'*80}")
        print(f"{d['label']} | target={d['target']} | new_oc={d['new_oc']}")
        print(f"  M1* top5: {d['m1_top5']}  (target rank #{d['m1_rank']})")
        print(f"  M2* top5: {d['m2_top5']}  (target rank #{d['m2_rank']})")
        print(f"  M3  top5: {d['m3_top5']}  (target rank {d['m3_rank']})")
        print(f"  M4  top5: {d['m4_top5']}  (target rank {d['m4_rank']})")
        print(f"  M5  top5: {d['m5_top5']}  (target rank #{d['m5_rank']})")

    # Save
    out = {"details": details, "summary": {
        mk: {"top1": hits[mk], "top3": top3[mk], "top5": top5[mk], "total": total_valid}
        for mk in ["m1", "m2", "m3", "m4", "m5"]
    }}
    Path("experiments/results/source_smoke_test.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to experiments/results/source_smoke_test.json")


if __name__ == "__main__":
    main()
