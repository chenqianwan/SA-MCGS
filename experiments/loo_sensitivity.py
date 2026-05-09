"""Leave-One-Out Sensitivity Analysis for Source Localization.

For each node X in the perturbed SCC:
  1. Remove X and its edges
  2. Re-detect SCCs on the remaining graph
  3. Run MCGS on the largest remaining SCC
  4. Record OC detection count

The node whose removal causes the LARGEST DROP in OC detections
is predicted as the perpetrator (source of the injected defect).

No clean comparison, no keyword hints, no prompt bias — pure effect-based.
"""
from __future__ import annotations

import asyncio
import copy
import json
import time
from pathlib import Path

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.models.graph import DependencyGraph, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.scc_sampler import SCCSampler
from src.modules.aggregator import Aggregator
from src.modules.risk_identifier import RiskIdentifier
from src.modules.pruning import DominancePruner
from src.modules.online_conformal_mcgs import OnlineConformalMCGS

from experiments.perturbation import perturb_type_c


RESULTS_DIR = Path("experiments/results")
CONCURRENCY = 4  # parallel MCGS runs to avoid API rate limits


async def run_mcgs_on_subset(
    llm_client, graph, config, clause_ids: list[str], label=""
) -> dict:
    """Run MCGS on a subset of clauses within the graph."""
    scc_set = set(clause_ids)
    sub_clauses = {cid: graph.clauses[cid] for cid in clause_ids if cid in graph.clauses}
    sub_edges = [e for e in graph.edges if e.source in scc_set and e.target in scc_set]

    sub_graph = DependencyGraph(
        contract_id="loo_sub", clauses=sub_clauses, edges=sub_edges,
        topological_order=[{"id": "scc_target", "type": "scc"}],
    )
    sub_scc = SCCInfo(
        id="scc_target", clause_ids=list(clause_ids),
        internal_edges=sub_edges, is_collapsed=False,
    )
    sub_graph.sccs = [sub_scc]

    n = len(clause_ids)
    num_samples = min(15, max(10, n // 2))
    num_rollouts = min(100, max(50, n * 3))

    ec = json.loads(json.dumps(config))
    ec["scc"]["num_samples"] = num_samples
    ec["mcgs"] = {
        "num_rollouts": num_rollouts,
        "ucb_exploration_weight": 1.414,
        "early_stopping": False,
    }
    ec.setdefault("pruning", {}).update({"cvar_alpha": 0.8, "cvar_safe_threshold": 0.4})
    ec["detection"] = {"alpha": 0.1, "min_rollouts": 5, "confidence_delta": 0.05}

    sampler = SCCSampler(llm_client, ec)
    oc_mcgs = OnlineConformalMCGS(ec)

    t0 = time.monotonic()
    scc_samples = await sampler.sample_all_sccs(sub_graph, {})
    tree = sampler.build_search_tree(sub_graph, scc_samples)
    DominancePruner(ec).prune(tree)

    active = {sid: nd for sid, nd in tree.nodes.items() if nd.active_branches}
    total_active = sum(len(nd.active_branches) for nd in active.values())
    rollout_results = oc_mcgs.search(tree, {}, sub_graph) if active and total_active else []

    agg = Aggregator(ec)
    result = agg.aggregate(rollout_results, {}, {}, sub_graph)
    result = RiskIdentifier(ec).identify(result, sub_graph)
    elapsed = time.monotonic() - t0

    oc = list(oc_mcgs.detected_clauses)
    hr = list(result.high_risk_clauses)

    details = {}
    for cid in clause_ids:
        cr = result.clause_results.get(cid)
        if cr:
            details[cid] = {
                "mean_score": cr.mean_risk_score,
                "max_score": cr.max_risk_score,
                "std_score": cr.std_risk_score,
                "is_oc_detected": cid in oc,
            }

    return {
        "label": label,
        "clause_ids": sorted(clause_ids),
        "n_clauses": n,
        "oc_detected": sorted(oc),
        "oc_count": len(oc),
        "hr_detected": sorted(hr),
        "hr_count": len(hr),
        "clause_details": details,
        "time": elapsed,
    }


async def run_loo_for_case(
    llm_client, graph, config, scc_clause_ids: list[str], target_id: str, label: str
) -> dict:
    """Run full LOO analysis: baseline + N leave-one-out MCGS runs."""
    n = len(scc_clause_ids)
    logger.info(f"\n{'='*70}")
    logger.info(f"LOO SENSITIVITY: {label} | target={target_id} | {n} nodes")
    logger.info(f"  Running baseline + {n} LOO iterations (concurrency={CONCURRENCY})")
    logger.info(f"{'='*70}")

    # 1. Baseline: full perturbed SCC
    logger.info("  Running baseline (full SCC)...")
    baseline = await run_mcgs_on_subset(
        llm_client, graph, config, scc_clause_ids, f"{label}_baseline"
    )
    baseline_oc = baseline["oc_count"]
    logger.info(f"  Baseline: OC={baseline_oc}, HR={baseline['hr_count']}")

    # 2. LOO: remove each node one at a time
    sem = asyncio.Semaphore(CONCURRENCY)

    async def loo_one(removed_id):
        async with sem:
            remaining = [c for c in scc_clause_ids if c != removed_id]
            result = await run_mcgs_on_subset(
                llm_client, graph, config, remaining,
                f"{label}_loo_{removed_id}"
            )
            result["removed_id"] = removed_id
            result["is_target"] = removed_id == target_id
            result["oc_drop"] = baseline_oc - result["oc_count"]
            logger.info(
                f"    LOO remove {removed_id:<12} → OC={result['oc_count']} "
                f"(drop={result['oc_drop']:+d}) "
                f"{'◀ TARGET' if removed_id == target_id else ''}"
            )
            return result

    loo_tasks = [loo_one(cid) for cid in scc_clause_ids]
    loo_results = await asyncio.gather(*loo_tasks)

    # 3. Rank by OC drop (highest drop = most likely perpetrator)
    loo_results.sort(key=lambda x: -x["oc_drop"])
    for i, r in enumerate(loo_results):
        r["rank"] = i + 1

    target_rank = next(
        (r["rank"] for r in loo_results if r["removed_id"] == target_id), n
    )
    target_oc_drop = next(
        (r["oc_drop"] for r in loo_results if r["removed_id"] == target_id), 0
    )

    logger.info(f"\n  LOO RANKING (by OC drop):")
    logger.info(f"  {'Rank':>4} | {'Removed':<12} | {'OC':>3} | {'Drop':>5} | {'Target?'}")
    logger.info(f"  {'-'*50}")
    for r in loo_results[:10]:
        marker = "◀ TARGET" if r["is_target"] else ""
        logger.info(
            f"  #{r['rank']:>3} | {r['removed_id']:<12} | {r['oc_count']:>3} | "
            f"{r['oc_drop']:>+4d}  | {marker}"
        )
    if target_rank > 10:
        tr = next(r for r in loo_results if r["is_target"])
        logger.info(f"  ...  (target at #{target_rank})")
        logger.info(
            f"  #{tr['rank']:>3} | {tr['removed_id']:<12} | {tr['oc_count']:>3} | "
            f"{tr['oc_drop']:>+4d}  | ◀ TARGET"
        )

    logger.info(f"\n  RESULT: target={target_id} ranked #{target_rank}/{n} "
                f"(OC drop={target_oc_drop:+d}, baseline OC={baseline_oc})")

    return {
        "label": label,
        "target_id": target_id,
        "scc_size": n,
        "baseline_oc": baseline_oc,
        "baseline_hr": baseline["hr_count"],
        "target_rank": target_rank,
        "target_oc_drop": target_oc_drop,
        "top5": [
            {"removed": r["removed_id"], "oc_count": r["oc_count"],
             "oc_drop": r["oc_drop"], "is_target": r["is_target"]}
            for r in loo_results[:5]
        ],
        "all_loo": [
            {"removed": r["removed_id"], "oc_count": r["oc_count"],
             "oc_drop": r["oc_drop"], "rank": r["rank"],
             "is_target": r["is_target"], "oc_detected": r["oc_detected"]}
            for r in loo_results
        ],
    }


async def main():
    logger.info("LOO SENSITIVITY ANALYSIS — Source Localization via Effect")
    logger.info("  Principle: remove each node, re-run MCGS, measure OC impact")

    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    llm_client = OpenAIClient(config["llm"])
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz"
    )
    DomainGraphPruner(config).prune(graph)
    graph = TarjanSCCDetector().detect(graph)

    results = []

    # Case 1: 5-node SCC (quick validation)
    target_5n = "bgb_240a"
    scc_5n = next(
        (s for s in graph.sccs if target_5n in s.clause_ids), None
    )
    if scc_5n:
        pg_5n = perturb_type_c(graph, scc_5n.clause_ids, target_5n)
        DomainGraphPruner(config).prune(pg_5n)
        pg_5n = TarjanSCCDetector().detect(pg_5n)
        pert_scc_5n = next(s for s in pg_5n.sccs if target_5n in s.clause_ids)

        r = await run_loo_for_case(
            llm_client, pg_5n, config, pert_scc_5n.clause_ids, target_5n, "5n_bgb_240a"
        )
        results.append(r)

    # Case 2: 24-node SCC (the real challenge)
    target_24n = "bgb_327o"
    scc_24n = next(
        (s for s in graph.sccs if target_24n in s.clause_ids), None
    )
    if scc_24n:
        pg_24n = perturb_type_c(graph, scc_24n.clause_ids, target_24n)
        DomainGraphPruner(config).prune(pg_24n)
        pg_24n = TarjanSCCDetector().detect(pg_24n)
        pert_scc_24n = next(s for s in pg_24n.sccs if target_24n in s.clause_ids)

        r = await run_loo_for_case(
            llm_client, pg_24n, config, pert_scc_24n.clause_ids, target_24n, "24n_bgb_327o"
        )
        results.append(r)

    # Summary
    print("\n" + "=" * 80)
    print("LOO SENSITIVITY — FINAL SUMMARY")
    print("=" * 80)
    print(f"{'Case':<20} | {'Target':<12} | {'Size':>4} | "
          f"{'Base OC':>7} | {'Tgt Rank':>8} | {'Tgt Drop':>8} | {'Top1':>12}")
    print("-" * 90)
    for r in results:
        top1 = r["top5"][0]["removed"] if r["top5"] else "—"
        hit = "✅" if r["target_rank"] == 1 else ""
        print(f"{r['label']:<20} | {r['target_id']:<12} | {r['scc_size']:>4} | "
              f"{r['baseline_oc']:>7} | #{r['target_rank']:>3}/{r['scc_size']:<3} | "
              f"{r['target_oc_drop']:>+7d} | {top1:<12} {hit}")

    # Save
    out = {"method": "LOO_sensitivity", "results": results}
    out_path = RESULTS_DIR / "loo_sensitivity.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to {out_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
