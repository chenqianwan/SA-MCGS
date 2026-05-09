"""Comprehensive validation suite for Risk Subgraph Extraction.

Three validation methods:
  V1 - Ablation:        Restore injected node to original, rerun MCGS,
                         check if risk signals disappear.
  V2 - Multi-Injection: Inject defects at 4 different locations in the
                         same 24n SCC, check if subgraph "follows" the
                         injection point each time.
  V3 - Oracle:          Compare clean-vs-perturbed risk deltas with the
                         extracted subgraph overlap (upper bound eval).
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.models.graph import DependencyGraph, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.alphago_mcgs import AlphaGoMCGS

from experiments.perturbation import perturb_type_c

RESULTS_DIR = Path("experiments/results")


# ── Shared helpers ───────────────────────────────────────────────────

def extract_subgraph(
    victims: set[str],
    edge_details: dict[str, dict],
    scc_ids: list[str],
    conflict_threshold: float = 0.3,
    max_hops: int = 3,
) -> dict:
    reverse_adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for _key, info in edge_details.items():
        src, tgt = info["source"], info["target"]
        avg_c = info["avg_conflict"]
        if avg_c >= conflict_threshold:
            reverse_adj[tgt].append((src, avg_c))

    subgraph_nodes = set(victims)
    paths: list[list[str]] = []

    for victim in victims:
        queue: deque[tuple[str, list[str], float]] = deque()
        queue.append((victim, [victim], 1.0))
        visited = {victim}
        while queue:
            node, path, score = queue.popleft()
            if len(path) > max_hops + 1:
                continue
            for upstream, edge_c in reverse_adj.get(node, []):
                if upstream in visited:
                    continue
                visited.add(upstream)
                new_path = path + [upstream]
                subgraph_nodes.add(upstream)
                if upstream not in victims:
                    paths.append(list(reversed(new_path)))
                queue.append((upstream, new_path, score * edge_c))

    return {
        "nodes": sorted(subgraph_nodes),
        "size": len(subgraph_nodes),
        "paths": sorted(paths, key=len)[:10],
    }


def pick_victims(oc_detected: set[str], ranking: list, top_k: int = 5):
    if oc_detected:
        return oc_detected, "oc"
    top_ids = {cid for cid, _ in ranking[:top_k]}
    return top_ids, "top_k"


async def run_mcgs(llm_client, graph, config, scc_info):
    n = len(scc_info.clause_ids)
    budget = min(400, max(60, n * 15))
    window_size = min(5, max(3, n // 6))

    ag_config = json.loads(json.dumps(config))
    ag_config["alphago_mcgs"] = {
        "budget": budget,
        "window_size": window_size,
        "concurrency": 6,
        "ucb_exploration_weight": 1.414,
        "ucb_exploration_init": 2.5,
        "virtual_loss_weight": 3,
        "temperature": 0.3,
        "max_tokens": 2048,
        "tt_max_reuse": 3,
        "dirichlet_alpha": 0.3,
        "dirichlet_weight": 0.25,
    }
    ag_config["detection"] = {"alpha": 0.1, "min_rollouts": 8}

    mcgs = AlphaGoMCGS(llm_client, ag_config)
    result = await mcgs.search(graph, scc_info)
    return result


def compute_overlap(set_a: set, set_b: set) -> dict:
    intersection = set_a & set_b
    union = set_a | set_b
    return {
        "intersection": sorted(intersection),
        "jaccard": len(intersection) / max(1, len(union)),
        "recall_a_in_b": len(intersection) / max(1, len(set_a)),
        "recall_b_in_a": len(intersection) / max(1, len(set_b)),
    }


# ── V1: Ablation (restore target, check signal disappears) ──────────

async def run_v1_ablation(llm_client, graph, config, scc, target_id):
    """Run MCGS on perturbed graph, then on clean graph (same SCC).
    Compare: does the risk signal disappear when defect is removed?"""
    logger.info(f"\n{'='*70}")
    logger.info(f"V1 ABLATION: inject={target_id}, then restore")
    logger.info(f"{'='*70}")

    n = len(scc.clause_ids)

    pg = perturb_type_c(graph, scc.clause_ids, target_id)
    DomainGraphPruner(config).prune(pg)
    pg = TarjanSCCDetector().detect(pg)
    pert_scc = next(s for s in pg.sccs if target_id in s.clause_ids)

    logger.info("  Running MCGS on perturbed graph ...")
    pert_result = await run_mcgs(llm_client, pg, config, pert_scc)

    logger.info("  Running MCGS on clean graph (same SCC) ...")
    clean_result = await run_mcgs(llm_client, graph, config, scc)

    pert_oc = set(pert_result["oc_detected_clauses"])
    clean_oc = set(clean_result["oc_detected_clauses"])

    pert_victims, _ = pick_victims(pert_oc, pert_result["ranking_by_risk"])
    clean_victims, _ = pick_victims(clean_oc, clean_result["ranking_by_risk"])

    pert_subgraph = extract_subgraph(
        pert_victims, pert_result.get("edge_details", {}), list(pert_scc.clause_ids)
    )
    clean_subgraph = extract_subgraph(
        clean_victims, clean_result.get("edge_details", {}), list(scc.clause_ids)
    )

    pert_top5_risk = {cid for cid, _ in pert_result["ranking_by_risk"][:5]}
    clean_top5_risk = {cid for cid, _ in clean_result["ranking_by_risk"][:5]}
    top5_overlap = compute_overlap(pert_top5_risk, clean_top5_risk)

    pert_scores = {cid: s for cid, s in pert_result["ranking_by_risk"]}
    clean_scores = {cid: s for cid, s in clean_result["ranking_by_risk"]}

    score_deltas = []
    for cid in scc.clause_ids:
        delta = pert_scores.get(cid, 0) - clean_scores.get(cid, 0)
        score_deltas.append({"clause_id": cid, "pert": pert_scores.get(cid, 0),
                             "clean": clean_scores.get(cid, 0), "delta": delta})
    score_deltas.sort(key=lambda x: -abs(x["delta"]))

    logger.info(f"\n  ABLATION RESULTS:")
    logger.info(f"    Perturbed OC: {sorted(pert_oc)} ({len(pert_oc)})")
    logger.info(f"    Clean OC:     {sorted(clean_oc)} ({len(clean_oc)})")
    logger.info(f"    Perturbed subgraph: {pert_subgraph['size']}/{n} nodes")
    logger.info(f"    Clean subgraph:     {clean_subgraph['size']}/{n} nodes")
    logger.info(f"    Top-5 risk overlap (Jaccard): {top5_overlap['jaccard']:.2f}")
    logger.info(f"    Top risk score deltas:")
    for sd in score_deltas[:8]:
        marker = " ◀ TARGET" if sd["clause_id"] == target_id else ""
        logger.info(f"      {sd['clause_id']:<12} clean={sd['clean']:.3f} "
                     f"pert={sd['pert']:.3f} Δ={sd['delta']:+.3f}{marker}")

    signal_disappeared = len(pert_oc - clean_oc) > 0 or top5_overlap["jaccard"] < 0.6

    return {
        "method": "V1_ablation",
        "target_id": target_id,
        "pert_oc": sorted(pert_oc),
        "clean_oc": sorted(clean_oc),
        "new_oc_from_injection": sorted(pert_oc - clean_oc),
        "pert_subgraph_nodes": pert_subgraph["nodes"],
        "clean_subgraph_nodes": clean_subgraph["nodes"],
        "pert_subgraph_size": pert_subgraph["size"],
        "clean_subgraph_size": clean_subgraph["size"],
        "top5_overlap": top5_overlap,
        "score_deltas": score_deltas[:10],
        "signal_disappeared": signal_disappeared,
    }


# ── V2: Multi-Injection Cross Validation ─────────────────────────────

async def run_v2_multi_inject(llm_client, graph, config, scc, target_ids: list[str]):
    """Inject defect at each target, extract subgraph, check if it follows."""
    logger.info(f"\n{'='*70}")
    logger.info(f"V2 MULTI-INJECTION: {len(target_ids)} injection points")
    logger.info(f"{'='*70}")

    n = len(scc.clause_ids)
    results = []

    for i, tid in enumerate(target_ids):
        logger.info(f"\n  --- Injection {i+1}/{len(target_ids)}: {tid} ---")

        pg = perturb_type_c(graph, scc.clause_ids, tid)
        DomainGraphPruner(config).prune(pg)
        pg = TarjanSCCDetector().detect(pg)
        pert_scc = next((s for s in pg.sccs if tid in s.clause_ids), None)
        if not pert_scc:
            logger.warning(f"  SCC broken for {tid}, skipping")
            continue

        result = await run_mcgs(llm_client, pg, config, pert_scc)

        oc = set(result["oc_detected_clauses"])
        victims, src = pick_victims(oc, result["ranking_by_risk"])
        subgraph = extract_subgraph(
            victims, result.get("edge_details", {}), list(pert_scc.clause_ids)
        )

        target_hit = tid in set(subgraph["nodes"])
        target_in_top5 = tid in {cid for cid, _ in result["ranking_by_risk"][:5]}

        hop_distance = None
        for path in subgraph["paths"]:
            if tid in path:
                hop_distance = len(path) - 1
                break

        neighbors_in_subgraph = []
        all_edges = result.get("edge_details", {})
        for key, info in all_edges.items():
            if info["source"] == tid and info["target"] in set(subgraph["nodes"]):
                neighbors_in_subgraph.append(info["target"])
            if info["target"] == tid and info["source"] in set(subgraph["nodes"]):
                neighbors_in_subgraph.append(info["source"])

        logger.info(f"    OC detected: {sorted(oc)} ({len(oc)})")
        logger.info(f"    Victims ({src}): {sorted(victims)}")
        logger.info(f"    Subgraph: {subgraph['size']}/{n} nodes")
        logger.info(f"    Target {tid} in subgraph: {'YES' if target_hit else 'NO'}")
        logger.info(f"    Target neighbors in subgraph: {neighbors_in_subgraph}")

        r = {
            "target_id": tid,
            "oc_detected": sorted(oc),
            "victims": sorted(victims),
            "victim_source": src,
            "subgraph_nodes": subgraph["nodes"],
            "subgraph_size": subgraph["size"],
            "subgraph_paths": subgraph["paths"][:5],
            "target_hit": target_hit,
            "target_in_top5": target_in_top5,
            "target_neighbors_in_subgraph": neighbors_in_subgraph,
            "hop_distance": hop_distance,
            "risk_ranking": result["ranking_by_risk"],
            "llm_calls": result.get("llm_calls", 0),
        }
        results.append(r)

    logger.info(f"\n  V2 SUMMARY:")
    logger.info(f"  {'Target':<12} | {'Subgraph':>8} | {'HIT':>3} | {'Neighbors':>9} | {'Top5':>4}")
    logger.info(f"  {'-'*50}")
    for r in results:
        logger.info(
            f"  {r['target_id']:<12} | "
            f"{r['subgraph_size']:>3}/{n:<3} | "
            f"{'YES' if r['target_hit'] else ' NO':>3} | "
            f"{len(r['target_neighbors_in_subgraph']):>9} | "
            f"{'YES' if r['target_in_top5'] else ' NO':>4}"
        )

    return {"method": "V2_multi_inject", "injections": results}


# ── V3: Oracle Evaluation (clean vs perturbed delta) ─────────────────

async def run_v3_oracle(llm_client, graph, config, scc, target_id):
    """Upper-bound evaluation: use clean-vs-perturbed deltas as ground truth,
    check overlap with the subgraph extracted from perturbed-only MCGS."""
    logger.info(f"\n{'='*70}")
    logger.info(f"V3 ORACLE: inject={target_id}")
    logger.info(f"{'='*70}")

    n = len(scc.clause_ids)

    pg = perturb_type_c(graph, scc.clause_ids, target_id)
    DomainGraphPruner(config).prune(pg)
    pg = TarjanSCCDetector().detect(pg)
    pert_scc = next(s for s in pg.sccs if target_id in s.clause_ids)

    clean_result, pert_result = await asyncio.gather(
        run_mcgs(llm_client, graph, config, scc),
        run_mcgs(llm_client, pg, config, pert_scc),
    )

    # Oracle: nodes whose risk changed significantly
    clean_scores = {cid: s for cid, s in clean_result["ranking_by_risk"]}
    pert_scores = {cid: s for cid, s in pert_result["ranking_by_risk"]}

    oracle_deltas = []
    for cid in scc.clause_ids:
        delta = pert_scores.get(cid, 0) - clean_scores.get(cid, 0)
        oracle_deltas.append({"clause_id": cid, "delta": delta,
                              "clean": clean_scores.get(cid, 0),
                              "pert": pert_scores.get(cid, 0)})
    oracle_deltas.sort(key=lambda x: -abs(x["delta"]))

    oracle_affected = {d["clause_id"] for d in oracle_deltas if abs(d["delta"]) > 0.03}
    oracle_top_affected = {d["clause_id"] for d in oracle_deltas[:8]}

    # Subgraph from perturbed-only (single version, no cheating)
    pert_oc = set(pert_result["oc_detected_clauses"])
    victims, src = pick_victims(pert_oc, pert_result["ranking_by_risk"])
    pert_subgraph = extract_subgraph(
        victims, pert_result.get("edge_details", {}), list(pert_scc.clause_ids)
    )

    subgraph_set = set(pert_subgraph["nodes"])
    overlap_affected = compute_overlap(subgraph_set, oracle_affected)
    overlap_top = compute_overlap(subgraph_set, oracle_top_affected)

    logger.info(f"\n  ORACLE RESULTS:")
    logger.info(f"    Oracle affected nodes (|Δ|>0.03): {sorted(oracle_affected)} ({len(oracle_affected)})")
    logger.info(f"    Oracle top-8 Δ nodes: {sorted(oracle_top_affected)}")
    logger.info(f"    Pert-only subgraph: {pert_subgraph['nodes']} ({pert_subgraph['size']})")
    logger.info(f"    Target {target_id} in oracle affected: {target_id in oracle_affected}")
    logger.info(f"    Target {target_id} in subgraph: {target_id in subgraph_set}")
    logger.info(f"    Overlap (subgraph ∩ oracle_affected):")
    logger.info(f"      Jaccard: {overlap_affected['jaccard']:.2f}")
    logger.info(f"      Recall(oracle in subgraph): {overlap_affected['recall_a_in_b']:.2f}")
    logger.info(f"      Recall(subgraph in oracle): {overlap_affected['recall_b_in_a']:.2f}")
    logger.info(f"    Top deltas:")
    for d in oracle_deltas[:10]:
        m1 = " ◀ TARGET" if d["clause_id"] == target_id else ""
        m2 = " ◀ IN_SUBGRAPH" if d["clause_id"] in subgraph_set else ""
        logger.info(f"      {d['clause_id']:<12} Δ={d['delta']:+.3f}{m1}{m2}")

    return {
        "method": "V3_oracle",
        "target_id": target_id,
        "oracle_affected": sorted(oracle_affected),
        "oracle_top8": sorted(oracle_top_affected),
        "oracle_deltas": oracle_deltas[:12],
        "subgraph_nodes": pert_subgraph["nodes"],
        "subgraph_size": pert_subgraph["size"],
        "target_in_oracle": target_id in oracle_affected,
        "target_in_subgraph": target_id in subgraph_set,
        "overlap_affected": overlap_affected,
        "overlap_top": overlap_top,
    }


# ── Main ─────────────────────────────────────────────────────────────

async def main():
    logger.info("=" * 70)
    logger.info("VALIDATION SUITE: 3 methods to verify subgraph quality")
    logger.info("=" * 70)

    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    llm_client = OpenAIClient(config["llm"])
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz"
    )
    DomainGraphPruner(config).prune(graph)
    graph = TarjanSCCDetector().detect(graph)

    scc_24 = next(s for s in graph.sccs if "bgb_327o" in s.clause_ids)
    all_results = {}

    # ── V1: Ablation ──
    logger.info("\n\n" + "=" * 70)
    logger.info("PHASE 1: ABLATION (inject bgb_327o → restore → compare)")
    logger.info("=" * 70)
    v1 = await run_v1_ablation(llm_client, graph, config, scc_24, "bgb_327o")
    all_results["V1_ablation"] = v1

    # ── V2: Multi-Injection ──
    logger.info("\n\n" + "=" * 70)
    logger.info("PHASE 2: MULTI-INJECTION (4 different injection points)")
    logger.info("=" * 70)
    inject_targets = ["bgb_327o", "bgb_312", "bgb_505", "bgb_358"]
    v2 = await run_v2_multi_inject(llm_client, graph, config, scc_24, inject_targets)
    all_results["V2_multi_inject"] = v2

    # ── V3: Oracle ──
    logger.info("\n\n" + "=" * 70)
    logger.info("PHASE 3: ORACLE EVALUATION (clean vs perturbed ground truth)")
    logger.info("=" * 70)
    v3 = await run_v3_oracle(llm_client, graph, config, scc_24, "bgb_327o")
    all_results["V3_oracle"] = v3

    # ── Final Summary ──
    print("\n" + "=" * 100)
    print("VALIDATION SUITE — FINAL SUMMARY")
    print("=" * 100)

    print("\n[V1] ABLATION: Does risk signal disappear when defect is removed?")
    print(f"  Perturbed OC:  {v1['pert_oc']} ({len(v1['pert_oc'])})")
    print(f"  Clean OC:      {v1['clean_oc']} ({len(v1['clean_oc'])})")
    print(f"  New OC (injection-caused): {v1['new_oc_from_injection']}")
    print(f"  Subgraph size: pert={v1['pert_subgraph_size']}, clean={v1['clean_subgraph_size']}")
    print(f"  Top-5 overlap:  Jaccard={v1['top5_overlap']['jaccard']:.2f}")
    print(f"  Signal disappeared: {'YES ✓' if v1['signal_disappeared'] else 'NO ✗'}")

    print(f"\n[V2] MULTI-INJECTION: Does subgraph follow the injection point?")
    print(f"  {'Target':<12} | {'SG Size':>7} | {'Hit':>3} | {'#Nbrs':>5} | {'Top5':>4} | Verdict")
    print(f"  {'-'*60}")
    for r in v2["injections"]:
        nbrs = len(r["target_neighbors_in_subgraph"])
        near = r["target_hit"] or nbrs >= 2
        print(
            f"  {r['target_id']:<12} | "
            f"{r['subgraph_size']:>3}/24  | "
            f"{'YES' if r['target_hit'] else ' NO':>3} | "
            f"{nbrs:>5} | "
            f"{'YES' if r['target_in_top5'] else ' NO':>4} | "
            f"{'PASS ✓' if near else 'MISS ✗'}"
        )

    print(f"\n[V3] ORACLE: Overlap between single-version subgraph and ground truth?")
    print(f"  Oracle affected ({len(v3['oracle_affected'])} nodes): {v3['oracle_affected']}")
    print(f"  Subgraph ({v3['subgraph_size']} nodes): {v3['subgraph_nodes']}")
    print(f"  Jaccard overlap: {v3['overlap_affected']['jaccard']:.2f}")
    print(f"  Recall(oracle→subgraph): {v3['overlap_affected']['recall_a_in_b']:.2f}")
    print(f"  Recall(subgraph→oracle): {v3['overlap_affected']['recall_b_in_a']:.2f}")
    print(f"  Target in oracle: {v3['target_in_oracle']}")
    print(f"  Target in subgraph: {v3['target_in_subgraph']}")

    # Save
    out_path = RESULTS_DIR / "validation_suite.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to {out_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
