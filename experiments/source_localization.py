"""Source Localization: Find the "perpetrator" from OC "victims".

Three methods:
  1. Neighbor Coverage  — who has the most new-OC neighbors?
  2. Rumor Center        — minimize graph distance to all new-OC nodes
                          (Shah & Zaman 2011, "Rumors in a Network")
  3. LLM Forensic        — feed structured evidence to LLM for reasoning

All methods use existing data — no new MCGS runs needed.
Method 3 uses a single focused LLM call per condition.
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from pathlib import Path

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.models.graph import DependencyGraph
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner


# ── Graph utilities ─────────────────────────────────────────────────


def build_adjacency(graph: DependencyGraph, scc_ids: set[str]):
    """Build adjacency list (directed + undirected) within SCC."""
    directed = defaultdict(set)   # source -> targets
    undirected = defaultdict(set)  # bidirectional neighbors
    for e in graph.edges:
        if e.source in scc_ids and e.target in scc_ids:
            directed[e.source].add(e.target)
            undirected[e.source].add(e.target)
            undirected[e.target].add(e.source)
    return directed, undirected


def bfs_distances(adj: dict[str, set[str]], source: str, nodes: set[str]):
    """BFS shortest distances from source to all reachable nodes."""
    dist = {source: 0}
    queue = deque([source])
    while queue:
        u = queue.popleft()
        for v in adj.get(u, []):
            if v not in dist and v in nodes:
                dist[v] = dist[u] + 1
                queue.append(v)
    return dist


# ── Method 1: Neighbor Coverage ─────────────────────────────────────


def neighbor_coverage(undirected: dict, all_ids: set[str], new_oc: set[str]):
    """Rank nodes by how many new-OC nodes are their direct neighbors."""
    scores = []
    for cid in sorted(all_ids):
        neighbors = undirected.get(cid, set())
        coverage = len(neighbors & new_oc)
        total_neighbors = len(neighbors)
        scores.append({
            "cid": cid,
            "coverage": coverage,
            "total_neighbors": total_neighbors,
            "ratio": coverage / total_neighbors if total_neighbors else 0,
            "is_new_oc_itself": cid in new_oc,
        })
    scores.sort(key=lambda x: (-x["coverage"], -x["ratio"]))
    return scores


# ── Method 2: Rumor Center ──────────────────────────────────────────


def rumor_center(undirected: dict, all_ids: set[str], new_oc: set[str]):
    """Find the node that minimizes total/max distance to all new-OC nodes.

    Inspired by Shah & Zaman (2011): the "rumor center" is the node
    that maximizes the likelihood of the observed infection pattern
    under a diffusion model. For simplicity, we use sum-of-distances
    and max-distance as proxy metrics.
    """
    if not new_oc:
        return []

    all_dists = {}
    for cid in all_ids:
        dists = bfs_distances(undirected, cid, all_ids)
        oc_dists = [dists.get(oc, 999) for oc in new_oc]
        all_dists[cid] = {
            "sum_dist": sum(oc_dists),
            "max_dist": max(oc_dists),
            "avg_dist": sum(oc_dists) / len(oc_dists),
            "reachable": sum(1 for d in oc_dists if d < 999),
        }

    scores = []
    for cid in sorted(all_ids):
        d = all_dists[cid]
        scores.append({
            "cid": cid,
            "sum_dist": d["sum_dist"],
            "max_dist": d["max_dist"],
            "avg_dist": d["avg_dist"],
            "reachable": d["reachable"],
        })

    scores.sort(key=lambda x: (x["sum_dist"], x["max_dist"]))
    return scores


# ── Method 3: LLM Forensic Reasoning ───────────────────────────────


def build_forensic_prompt(
    all_ids: list[str],
    edges: list[tuple[str, str]],
    new_oc: list[str],
    clean_oc: list[str],
    delta_scores: dict,
    scc_size: int,
):
    """Build a focused prompt for LLM to identify the source of perturbation."""
    edge_str = "\n".join(f"  {s} → {t}" for s, t in edges)
    new_oc_str = ", ".join(new_oc) if new_oc else "None"
    clean_oc_str = ", ".join(clean_oc) if clean_oc else "None"

    top_delta = sorted(delta_scores.items(), key=lambda x: -x[1])[:5]
    delta_str = "\n".join(f"  {cid}: Δμ = {d:+.4f}" for cid, d in top_delta)

    return (
        "You are a forensic analyst for legal document systems.\n\n"
        "A set of interdependent legal clauses forms a Strongly Connected Component (SCC) "
        f"with {scc_size} nodes. We ran a statistical anomaly detection system (Online Conformal "
        "Prediction) on two versions of this SCC:\n"
        "  - CLEAN version: the original, unmodified legal text\n"
        "  - PERTURBED version: one clause was subtly modified (scope expansion)\n\n"
        "The anomaly detector flagged certain nodes as statistically anomalous.\n\n"
        f"## Dependency Graph (directed edges within SCC)\n{edge_str}\n\n"
        f"## Anomaly Detection Results\n"
        f"  Nodes flagged in CLEAN only: {clean_oc_str}\n"
        f"  Nodes flagged in PERTURBED only (NEW anomalies): {new_oc_str}\n\n"
        f"## Risk Score Changes (top 5 by increase)\n{delta_str}\n\n"
        "## Task\n"
        "Based on the dependency graph structure and the pattern of NEW anomalies, "
        "identify which single node is most likely the SOURCE of the perturbation "
        "(the one whose text was modified). The modified node itself may or may not "
        "appear in the anomaly list — often the modification causes its NEIGHBORS "
        "to become anomalous rather than the source itself.\n\n"
        "Reason about:\n"
        "1. Which node is most central to the new anomaly pattern?\n"
        "2. Which node's modification could cause the observed cascade?\n"
        "3. The dependency directions matter: a source change propagates forward.\n\n"
        "Output STRICTLY as JSON:\n"
        '{"source_node": "<clause_id>", "confidence": 0.0-1.0, '
        '"reasoning": "brief explanation", '
        '"top3_suspects": ["<id1>", "<id2>", "<id3>"]}'
    )


async def llm_forensic_single(llm_client, prompt):
    try:
        resp = await llm_client.call_json(prompt, temperature=0.0, max_tokens=2048)
        return resp
    except Exception as e:
        logger.warning(f"LLM forensic failed: {e}")
        return {"source_node": "unknown", "confidence": 0, "reasoning": str(e), "top3_suspects": []}


# ── Main Analysis ───────────────────────────────────────────────────


async def main():
    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    # Load graph for structure
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz"
    )
    DomainGraphPruner(config).prune(graph)
    graph = TarjanSCCDetector().detect(graph)

    # Load ablation results
    with open("experiments/results/ablation_suite.json") as f:
        ablation = json.load(f)

    all_cases = []
    for key in ["exp1_cross_scale", "exp2_multi_target", "exp3_repeated"]:
        all_cases.extend(ablation.get(key, []))

    llm_client = OpenAIClient(config["llm"])

    print("=" * 110)
    print("SOURCE LOCALIZATION: Finding the Perpetrator from OC Victims")
    print("  Method 1: Neighbor Coverage (graph topology)")
    print("  Method 2: Rumor Center (Shah & Zaman 2011)")
    print("  Method 3: LLM Forensic Reasoning (single focused call)")
    print("=" * 110)

    results = []
    llm_tasks = []

    for case in all_cases:
        target_id = case["target_id"]
        scc_ids = set(case["scc_clause_ids"])
        label = case["label"]

        clean_oc = set(case["clean_mcgs"]["oc_detected_clauses"])
        pert_oc = set(case["pert_mcgs"]["oc_detected_clauses"])
        new_oc = pert_oc - clean_oc
        lost_oc = clean_oc - pert_oc

        if not new_oc:
            results.append({
                "label": label, "target": target_id, "scc_size": len(scc_ids),
                "new_oc_count": 0,
                "m1_rank": None, "m1_top1": None,
                "m2_rank": None, "m2_top1": None,
                "m3_source": None, "m3_top3": [],
            })
            continue

        directed, undirected = build_adjacency(graph, scc_ids)

        # Extract edges for LLM prompt
        edges = []
        for s in sorted(scc_ids):
            for t in sorted(directed.get(s, [])):
                edges.append((s, t))

        # Delta scores
        clean_details = case["clean_mcgs"]["clause_details"]
        pert_details = case["pert_mcgs"]["clause_details"]
        delta_scores = {}
        for cid in scc_ids:
            cm = clean_details.get(cid, {}).get("mean_score", 0)
            pm = pert_details.get(cid, {}).get("mean_score", 0)
            delta_scores[cid] = pm - cm

        # Method 1: Neighbor Coverage
        m1 = neighbor_coverage(undirected, scc_ids, new_oc)
        m1_rank = next((i+1 for i, s in enumerate(m1) if s["cid"] == target_id), len(scc_ids))
        m1_top1 = m1[0]["cid"] if m1 else None

        # Method 2: Rumor Center
        m2 = rumor_center(undirected, scc_ids, new_oc)
        m2_rank = next((i+1 for i, s in enumerate(m2) if s["cid"] == target_id), len(scc_ids))
        m2_top1 = m2[0]["cid"] if m2 else None

        # Method 3: Prepare LLM prompt (run later in parallel)
        prompt = build_forensic_prompt(
            sorted(scc_ids), edges, sorted(new_oc), sorted(lost_oc),
            delta_scores, len(scc_ids)
        )
        llm_tasks.append((label, target_id, len(scc_ids), new_oc, m1, m1_rank, m1_top1, m2, m2_rank, m2_top1, prompt))

    # Run all LLM forensic calls in parallel
    llm_responses = await asyncio.gather(*[
        llm_forensic_single(llm_client, t[-1]) for t in llm_tasks
    ])

    # Combine results
    for (label, target_id, scc_size, new_oc, m1, m1_rank, m1_top1, m2, m2_rank, m2_top1, _), llm_resp in zip(llm_tasks, llm_responses):
        m3_source = llm_resp.get("source_node", "unknown")
        m3_top3 = llm_resp.get("top3_suspects", [])
        m3_rank = None
        if m3_source == target_id:
            m3_rank = 1
        elif target_id in m3_top3:
            m3_rank = m3_top3.index(target_id) + 1
        else:
            m3_rank = len(m3_top3) + 1  # not in top3

        m3_confidence = llm_resp.get("confidence", 0)
        m3_reasoning = llm_resp.get("reasoning", "")[:120]

        results.append({
            "label": label, "target": target_id, "scc_size": scc_size,
            "new_oc_count": len(new_oc), "new_oc": sorted(new_oc),
            "m1_rank": m1_rank, "m1_top1": m1_top1,
            "m1_top3": [s["cid"] for s in m1[:3]],
            "m1_detail": [(s["cid"], s["coverage"], s["ratio"]) for s in m1[:5]],
            "m2_rank": m2_rank, "m2_top1": m2_top1,
            "m2_top3": [s["cid"] for s in m2[:3]],
            "m2_detail": [(s["cid"], s["sum_dist"], s["avg_dist"]) for s in m2[:5]],
            "m3_source": m3_source, "m3_top3": m3_top3,
            "m3_confidence": m3_confidence, "m3_reasoning": m3_reasoning,
            "m3_rank": m3_rank,
        })

    # ── Print Results ───────────────────────────────────────────────
    print(f"\n{'Label':<32} | {'Size':>4} | {'Target':<12} | {'#NewOC':>6} | "
          f"{'M1 Rank':>8} {'M1 Top1':<12} | {'M2 Rank':>8} {'M2 Top1':<12} | "
          f"{'M3 Rank':>8} {'M3 Source':<12}")
    print("-" * 140)

    m1_hits = m2_hits = m3_hits = 0
    m1_top3 = m2_top3 = m3_top3_hits = 0
    total_valid = 0

    for r in results:
        if r["new_oc_count"] == 0:
            print(f"{r['label']:<32} | {r['scc_size']:>4} | {r['target']:<12} | {'—':>6} | "
                  f"{'—':>8} {'—':<12} | {'—':>8} {'—':<12} | {'—':>8} {'—':<12}")
            continue

        total_valid += 1
        if r["m1_rank"] == 1: m1_hits += 1
        if r["m1_rank"] and r["m1_rank"] <= 3: m1_top3 += 1
        if r["m2_rank"] == 1: m2_hits += 1
        if r["m2_rank"] and r["m2_rank"] <= 3: m2_top3 += 1
        if r.get("m3_source") == r["target"]: m3_hits += 1
        if r.get("m3_rank") and r["m3_rank"] <= 3: m3_top3_hits += 1

        m1_hit = "✅" if r["m1_rank"] == 1 else f"#{r['m1_rank']}"
        m2_hit = "✅" if r["m2_rank"] == 1 else f"#{r['m2_rank']}"
        m3_hit = "✅" if r.get("m3_source") == r["target"] else f"#{r.get('m3_rank', '?')}"

        print(f"{r['label']:<32} | {r['scc_size']:>4} | {r['target']:<12} | {r['new_oc_count']:>6} | "
              f"{m1_hit:>8} {r['m1_top1']:<12} | {m2_hit:>8} {r['m2_top1']:<12} | "
              f"{m3_hit:>8} {r.get('m3_source','?'):<12}")

    print("-" * 140)
    print(f"\n{'METHOD':<25} | {'Top-1 Hit':>10} | {'Top-3 Hit':>10} | {'Total Valid':>12}")
    print("-" * 65)
    print(f"{'M1: Neighbor Coverage':<25} | {m1_hits}/{total_valid} ({m1_hits/total_valid:.0%}):>10 | "
          f"{m1_top3}/{total_valid} ({m1_top3/total_valid:.0%}):>10 | {total_valid:>12}")
    print(f"{'M2: Rumor Center':<25} | {m2_hits}/{total_valid} ({m2_hits/total_valid:.0%}):>10 | "
          f"{m2_top3}/{total_valid} ({m2_top3/total_valid:.0%}):>10 | {total_valid:>12}")
    print(f"{'M3: LLM Forensic':<25} | {m3_hits}/{total_valid} ({m3_hits/total_valid:.0%}):>10 | "
          f"{m3_top3_hits}/{total_valid} ({m3_top3_hits/total_valid:.0%}):>10 | {total_valid:>12}")

    # ── Detailed per-case analysis ──────────────────────────────────
    for r in results:
        if r["new_oc_count"] == 0:
            continue
        print(f"\n{'─'*80}")
        print(f"Case: {r['label']} | Target: {r['target']} | New OC: {r.get('new_oc', [])}")
        print(f"  M1 Neighbor Coverage (top 5):")
        for cid, cov, ratio in r.get("m1_detail", []):
            marker = " ◀ TARGET" if cid == r["target"] else ""
            print(f"    {cid:<12} coverage={cov}, ratio={ratio:.2f}{marker}")
        print(f"  M2 Rumor Center (top 5):")
        for cid, sdist, adist in r.get("m2_detail", []):
            marker = " ◀ TARGET" if cid == r["target"] else ""
            print(f"    {cid:<12} sum_dist={sdist}, avg_dist={adist:.2f}{marker}")
        print(f"  M3 LLM Forensic:")
        print(f"    Source: {r.get('m3_source', '?')} (conf={r.get('m3_confidence', 0):.2f})")
        print(f"    Top3: {r.get('m3_top3', [])}")
        print(f"    Reasoning: {r.get('m3_reasoning', '—')}")

    # Save
    out = {"results": results, "summary": {
        "m1_top1": f"{m1_hits}/{total_valid}",
        "m1_top3": f"{m1_top3}/{total_valid}",
        "m2_top1": f"{m2_hits}/{total_valid}",
        "m2_top3": f"{m2_top3}/{total_valid}",
        "m3_top1": f"{m3_hits}/{total_valid}",
        "m3_top3": f"{m3_top3_hits}/{total_valid}",
    }}
    Path("experiments/results/source_localization.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"\nResults saved to experiments/results/source_localization.json")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
