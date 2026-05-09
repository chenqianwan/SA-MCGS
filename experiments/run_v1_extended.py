"""V1 Extended Ablation: multiple injection points.

Key insight: the clean MCGS run is the SAME for all injection points
(same original SCC), so we only run clean ONCE and reuse it.
For perturbed runs, we reuse results from V2 where available.
Only new perturbed runs are needed for targets not in V2.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from pathlib import Path

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

INJECT_TARGETS = [
    "bgb_327o", "bgb_312", "bgb_505", "bgb_358",
    "bgb_327", "bgb_312g", "bgb_507", "bgb_504",
    "bgb_506", "bgb_327m", "bgb_491a", "bgb_356",
    "bgb_327b", "bgb_512", "bgb_515", "bgb_513",
]


def extract_subgraph(victims, edge_details, scc_ids,
                     conflict_threshold=0.3, max_hops=3):
    reverse_adj = defaultdict(list)
    for _key, info in edge_details.items():
        if info["avg_conflict"] >= conflict_threshold:
            reverse_adj[info["target"]].append(info["source"])

    subgraph_nodes = set(victims)
    for victim in victims:
        queue = deque([(victim, 0)])
        visited = {victim}
        while queue:
            node, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for upstream in reverse_adj.get(node, []):
                if upstream not in visited:
                    visited.add(upstream)
                    subgraph_nodes.add(upstream)
                    queue.append((upstream, depth + 1))

    return {"nodes": sorted(subgraph_nodes), "size": len(subgraph_nodes)}


def pick_victims(oc_detected, ranking, top_k=5):
    if oc_detected:
        return set(oc_detected), "oc"
    return {cid for cid, _ in ranking[:top_k]}, "top_k"


async def run_mcgs(llm_client, graph, config, scc_info):
    n = len(scc_info.clause_ids)
    budget = min(400, max(60, n * 15))
    window_size = min(5, max(3, n // 6))

    ag_config = json.loads(json.dumps(config))
    ag_config["alphago_mcgs"] = {
        "budget": budget, "window_size": window_size,
        "concurrency": 6, "ucb_exploration_weight": 1.414,
        "ucb_exploration_init": 2.5, "virtual_loss_weight": 3,
        "temperature": 0.3, "max_tokens": 2048,
        "tt_max_reuse": 3, "dirichlet_alpha": 0.3,
        "dirichlet_weight": 0.25,
    }
    ag_config["detection"] = {"alpha": 0.1, "min_rollouts": 8}

    mcgs = AlphaGoMCGS(llm_client, ag_config)
    return await mcgs.search(graph, scc_info)


async def main():
    logger.info("=" * 70)
    logger.info("V1 EXTENDED ABLATION — 16 injection points")
    logger.info("  Clean MCGS runs once, reused for all comparisons")
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
    n = len(scc_24.clause_ids)

    # ── Step 1: Run clean MCGS 3 times for stability (sequential to avoid rate limits) ──
    logger.info("\nStep 1: Running clean MCGS (3 runs, sequential) ...")
    clean_runs = []
    for ci in range(3):
        logger.info(f"  Clean run {ci+1}/3 ...")
        cr = await run_mcgs(llm_client, graph, config, scc_24)
        clean_runs.append(cr)
        logger.info(f"  Clean run {ci+1} done: OC={cr['oc_detected_clauses']}")

    clean_avg_scores = {}
    for cid in scc_24.clause_ids:
        scores = []
        for cr in clean_runs:
            for c, s in cr["ranking_by_risk"]:
                if c == cid:
                    scores.append(s)
        clean_avg_scores[cid] = sum(scores) / max(1, len(scores))

    clean_oc_union = set()
    for cr in clean_runs:
        clean_oc_union.update(cr["oc_detected_clauses"])

    clean_subgraphs = []
    for cr in clean_runs:
        oc = set(cr["oc_detected_clauses"])
        victims, _ = pick_victims(oc, cr["ranking_by_risk"])
        sg = extract_subgraph(victims, cr.get("edge_details", {}),
                              list(scc_24.clause_ids))
        clean_subgraphs.append(sg)

    avg_clean_sg = sum(sg["size"] for sg in clean_subgraphs) / len(clean_subgraphs)

    logger.info(f"  Clean OC (union of 3 runs): {sorted(clean_oc_union)}")
    logger.info(f"  Clean avg subgraph size: {avg_clean_sg:.1f}/{n}")
    logger.info(f"  Clean avg scores (top 5):")
    for cid, s in sorted(clean_avg_scores.items(), key=lambda x: -x[1])[:5]:
        logger.info(f"    {cid:<12} avg_risk={s:.3f}")

    # ── Step 2: Run perturbed MCGS for each injection (2 concurrent) ──
    logger.info(f"\nStep 2: Running perturbed MCGS for {len(INJECT_TARGETS)} injections ...")

    sem = asyncio.Semaphore(2)

    async def run_one_injection(tid, idx):
        async with sem:
            logger.info(f"  [{idx}/{len(INJECT_TARGETS)}] Injecting {tid} ...")
            t0 = time.monotonic()
            try:
                pg = perturb_type_c(graph, scc_24.clause_ids, tid)
                DomainGraphPruner(config).prune(pg)
                pg = TarjanSCCDetector().detect(pg)
                pert_scc = next((s for s in pg.sccs if tid in s.clause_ids), None)
                if not pert_scc:
                    return None
                result = await run_mcgs(llm_client, pg, config, pert_scc)
                elapsed = time.monotonic() - t0
                logger.info(f"  [{idx}] {tid} done ({elapsed:.0f}s)")
                return {"target_id": tid, "result": result, "time": elapsed}
            except Exception as e:
                logger.error(f"  [{idx}] {tid} failed: {e}")
                return None

    tasks = [run_one_injection(tid, i+1) for i, tid in enumerate(INJECT_TARGETS)]
    raw = await asyncio.gather(*tasks)
    pert_runs = {r["target_id"]: r for r in raw if r is not None}

    # ── Step 3: Compute ablation metrics ──
    logger.info(f"\nStep 3: Computing ablation metrics ...")

    results = []
    for tid in INJECT_TARGETS:
        if tid not in pert_runs:
            continue

        pr = pert_runs[tid]["result"]
        pert_oc = set(pr["oc_detected_clauses"])
        pert_victims, pert_src = pick_victims(pert_oc, pr["ranking_by_risk"])
        pert_sg = extract_subgraph(pert_victims, pr.get("edge_details", {}),
                                   list(scc_24.clause_ids))

        pert_scores = {cid: s for cid, s in pr["ranking_by_risk"]}

        new_oc = pert_oc - clean_oc_union
        disappeared_oc = clean_oc_union - pert_oc

        score_deltas = []
        for cid in scc_24.clause_ids:
            delta = pert_scores.get(cid, 0) - clean_avg_scores.get(cid, 0)
            score_deltas.append({
                "clause_id": cid, "delta": delta,
                "clean": clean_avg_scores.get(cid, 0),
                "pert": pert_scores.get(cid, 0),
            })
        score_deltas.sort(key=lambda x: -abs(x["delta"]))

        sg_expansion = pert_sg["size"] - avg_clean_sg

        pert_top5 = {cid for cid, _ in pr["ranking_by_risk"][:5]}
        clean_top5_avg = set()
        for cr in clean_runs:
            for cid, _ in cr["ranking_by_risk"][:5]:
                clean_top5_avg.add(cid)
        top5_jaccard = len(pert_top5 & clean_top5_avg) / max(1, len(pert_top5 | clean_top5_avg))

        results.append({
            "target_id": tid,
            "pert_oc": sorted(pert_oc),
            "pert_oc_count": len(pert_oc),
            "new_oc": sorted(new_oc),
            "new_oc_count": len(new_oc),
            "pert_sg_size": pert_sg["size"],
            "clean_sg_avg": round(avg_clean_sg, 1),
            "sg_expansion": round(sg_expansion, 1),
            "top5_jaccard": round(top5_jaccard, 2),
            "top_deltas": score_deltas[:5],
            "target_delta": next(
                (d for d in score_deltas if d["clause_id"] == tid), None
            ),
        })

    # ── Print results ──
    print("\n" + "=" * 110)
    print("V1 EXTENDED ABLATION — COMPREHENSIVE RESULTS")
    print("=" * 110)
    print(f"Clean baseline: OC={sorted(clean_oc_union)}, avg SG={avg_clean_sg:.1f}/{n}")
    print()
    print(f"{'#':>2} {'Target':<12} | {'Pert OC':>7} | {'New OC':>6} | "
          f"{'Pert SG':>7} | {'Expand':>6} | {'T5 Jac':>6} | "
          f"{'Target Δ':>8} | Verdict")
    print("-" * 110)

    strong_signal = 0
    for i, r in enumerate(results):
        td = r["target_delta"]
        td_str = f"{td['delta']:+.3f}" if td else "  N/A"
        expansion = r["sg_expansion"]
        has_signal = (r["new_oc_count"] > 0 or expansion > 3 or r["top5_jaccard"] < 0.5)
        if has_signal:
            strong_signal += 1
        verdict = "SIGNAL" if has_signal else "weak"

        print(
            f"{i+1:>2} {r['target_id']:<12} | "
            f"{r['pert_oc_count']:>7} | "
            f"{r['new_oc_count']:>6} | "
            f"{r['pert_sg_size']:>3}/{n:<3} | "
            f"{expansion:>+5.1f} | "
            f"{r['top5_jaccard']:>5.2f} | "
            f"{td_str:>8} | "
            f"{verdict}"
        )

    print("-" * 110)
    print(f"TOTAL: {len(results)} injections | "
          f"Strong signal: {strong_signal}/{len(results)} ({strong_signal/len(results):.0%})")
    print(f"  Clean avg SG: {avg_clean_sg:.1f} | "
          f"Pert avg SG: {sum(r['pert_sg_size'] for r in results)/len(results):.1f}")

    out_path = RESULTS_DIR / "v1_extended.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "method": "V1_extended_ablation",
        "clean_oc_union": sorted(clean_oc_union),
        "clean_avg_sg": avg_clean_sg,
        "clean_avg_scores": clean_avg_scores,
        "results": results,
    }, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to {out_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
