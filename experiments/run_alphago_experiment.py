"""AlphaGo-style MCGS experiment: single-step greedy search vs old MCGS.

Runs on the same test cases as LOO experiment (5n + 24n) with Type C
perturbation. Compares source localization accuracy using:
  - OC detection
  - Conflict fan-out ranking
  - Risk ranking
"""
from __future__ import annotations

import asyncio
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
from src.modules.alphago_mcgs import AlphaGoMCGS

from experiments.perturbation import perturb_type_c

RESULTS_DIR = Path("experiments/results")


async def run_alphago_on_scc(
    llm_client, graph, config, scc_info, label=""
) -> dict:
    """Run AlphaGo-style MCGS on an SCC."""
    n = len(scc_info.clause_ids)
    budget = min(400, max(60, n * 15))
    window_size = min(5, max(3, n // 6))

    ag_config = json.loads(json.dumps(config))
    ag_config["alphago_mcgs"] = {
        "budget": budget,
        "window_size": window_size,
        "concurrency": 6,
        "ucb_exploration_weight": 1.414,
        "virtual_loss_weight": 3,
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    ag_config["detection"] = {"alpha": 0.1, "min_rollouts": 8, "confidence_delta": 0.05}

    mcgs = AlphaGoMCGS(llm_client, ag_config)
    result = await mcgs.search(graph, scc_info)
    result["label"] = label
    return result


def get_rank(ranking: list, target_id: str) -> int:
    for i, item in enumerate(ranking):
        if item[0] == target_id:
            return i + 1
    return len(ranking)


async def run_case(llm_client, graph, config, target_id, label):
    """Run both clean and perturbed AlphaGo MCGS for one case."""
    scc = next((s for s in graph.sccs if target_id in s.clause_ids), None)
    if not scc:
        logger.error(f"Cannot find SCC for {target_id}")
        return None

    logger.info(f"\n{'='*70}")
    logger.info(f"CASE: {label} | target={target_id} | scc_size={len(scc.clause_ids)}")
    logger.info(f"{'='*70}")

    pg = perturb_type_c(graph, scc.clause_ids, target_id)
    DomainGraphPruner(config).prune(pg)
    pg = TarjanSCCDetector().detect(pg)
    pert_scc = next((s for s in pg.sccs if target_id in s.clause_ids), None)
    if not pert_scc:
        logger.error(f"Cannot find perturbed SCC for {target_id}")
        return None

    t0 = time.monotonic()
    clean_result, pert_result = await asyncio.gather(
        run_alphago_on_scc(llm_client, graph, config, scc, f"clean_{label}"),
        run_alphago_on_scc(llm_client, pg, config, pert_scc, f"pert_{label}"),
    )
    elapsed = time.monotonic() - t0

    n = len(scc.clause_ids)
    risk_rank = get_rank(pert_result["ranking_by_risk"], target_id)
    conflict_rank = get_rank(pert_result["ranking_by_conflict_rate"], target_id)
    fanout_rank = get_rank(pert_result["ranking_by_fanout"], target_id)

    clean_oc = set(clean_result["oc_detected_clauses"])
    pert_oc = set(pert_result["oc_detected_clauses"])
    new_oc = sorted(pert_oc - clean_oc)
    target_in_oc = target_id in pert_oc
    target_in_new_oc = target_id in new_oc

    logger.info(f"\n  RESULTS for {label}:")
    logger.info(f"  Clean OC: {sorted(clean_oc)} ({len(clean_oc)})")
    logger.info(f"  Pert  OC: {sorted(pert_oc)} ({len(pert_oc)})")
    logger.info(f"  New   OC: {new_oc} ({len(new_oc)})")
    logger.info(f"  Target in OC: {target_in_oc} | in new OC: {target_in_new_oc}")
    logger.info(f"  Risk rank:     #{risk_rank}/{n}")
    logger.info(f"  Conflict rank: #{conflict_rank}/{n}")
    logger.info(f"  Fanout rank:   #{fanout_rank}/{n}")
    logger.info(f"  Total time: {elapsed:.1f}s")

    # Show top 5 for each ranking
    logger.info(f"\n  Top 5 by risk score:")
    for i, (cid, score) in enumerate(pert_result["ranking_by_risk"][:5]):
        marker = " ◀ TARGET" if cid == target_id else ""
        logger.info(f"    #{i+1} {cid:<12} risk={score:.3f}{marker}")

    logger.info(f"  Top 5 by conflict rate:")
    for i, (cid, rate) in enumerate(pert_result["ranking_by_conflict_rate"][:5]):
        marker = " ◀ TARGET" if cid == target_id else ""
        logger.info(f"    #{i+1} {cid:<12} conflict_rate={rate:.3f}{marker}")

    logger.info(f"  Top 5 by conflict fanout:")
    for i, (cid, info) in enumerate(pert_result["ranking_by_fanout"][:5]):
        marker = " ◀ TARGET" if cid == target_id else ""
        logger.info(f"    #{i+1} {cid:<12} avg_conflict={info['avg_conflict']:.3f}{marker}")

    return {
        "label": label,
        "target_id": target_id,
        "scc_size": n,
        "clean_oc": sorted(clean_oc),
        "pert_oc": sorted(pert_oc),
        "new_oc": new_oc,
        "clean_oc_count": len(clean_oc),
        "pert_oc_count": len(pert_oc),
        "new_oc_count": len(new_oc),
        "target_in_oc": target_in_oc,
        "target_in_new_oc": target_in_new_oc,
        "risk_rank": risk_rank,
        "conflict_rank": conflict_rank,
        "fanout_rank": fanout_rank,
        "risk_top5": [(c, s) for c, s in pert_result["ranking_by_risk"][:5]],
        "conflict_top5": [(c, s) for c, s in pert_result["ranking_by_conflict_rate"][:5]],
        "fanout_top5": [(c, i) for c, i in pert_result["ranking_by_fanout"][:5]],
        "pert_llm_calls": pert_result["llm_calls"],
        "pert_tt_hits": pert_result["tt_hits"],
        "pert_tt_hit_rate": pert_result["tt_hit_rate"],
        "time": elapsed,
        "clean_result": clean_result,
        "pert_result": pert_result,
    }


async def main():
    logger.info("=" * 70)
    logger.info("ALPHAGO-STYLE MCGS EXPERIMENT")
    logger.info("  Single-step greedy search with transposition table")
    logger.info("  Virtual Loss parallelism for concurrent exploration")
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

    results = []

    # Case 1: 5n
    r = await run_case(llm_client, graph, config, "bgb_240a", "5n_bgb_240a")
    if r:
        results.append(r)

    # Case 2: 24n
    r = await run_case(llm_client, graph, config, "bgb_327o", "24n_bgb_327o")
    if r:
        results.append(r)

    # Summary
    print("\n" + "=" * 100)
    print("ALPHAGO-STYLE MCGS — FINAL SUMMARY")
    print("=" * 100)
    print(f"{'Case':<20} | {'Target':<12} | {'Size':>4} | "
          f"{'OC Δ':>5} | {'Risk':>6} | {'Conflict':>8} | {'Fanout':>7} | "
          f"{'LLM':>4} | {'TT%':>5} | {'Time':>6}")
    print("-" * 100)

    for r in results:
        risk_mark = "✅" if r["risk_rank"] <= 3 else f"#{r['risk_rank']}"
        conf_mark = "✅" if r["conflict_rank"] <= 3 else f"#{r['conflict_rank']}"
        fan_mark = "✅" if r["fanout_rank"] <= 3 else f"#{r['fanout_rank']}"
        print(
            f"{r['label']:<20} | {r['target_id']:<12} | {r['scc_size']:>4} | "
            f"{r['new_oc_count']:>+4d} | "
            f"{risk_mark:>6} | {conf_mark:>8} | {fan_mark:>7} | "
            f"{r['pert_llm_calls']:>4} | {r['pert_tt_hit_rate']:>4.0%} | "
            f"{r['time']:>5.0f}s"
        )

    # Comparison with old methods
    print(f"\n{'='*80}")
    print("COMPARISON: Source Localization Rankings (24n only)")
    print("=" * 80)
    r24 = next((r for r in results if "24n" in r["label"]), None)
    if r24:
        print(f"{'Method':<40} | {'Target Rank':>11}")
        print("-" * 55)
        print(f"{'M1  Neighbor Coverage (undirected)':<40} | #15-20/24")
        print(f"{'M2  Rumor Center':<40} |   #22/24")
        print(f"{'M1* Forward Reachability (directed)':<40} |   #15/24")
        print(f"{'M2* Reverse Propagation (directed)':<40} |   #15/24")
        print(f"{'LOO Sensitivity':<40} |    #9/24")
        print(f"{'AG  Risk Score':<40} | #{r24['risk_rank']:>4}/24")
        print(f"{'AG  Conflict Rate':<40} | #{r24['conflict_rank']:>4}/24")
        print(f"{'AG  Conflict Fanout':<40} | #{r24['fanout_rank']:>4}/24")

    # Save
    save_results = []
    for r in results:
        save_r = {k: v for k, v in r.items() if k not in ("clean_result", "pert_result")}
        save_r["clean_oc_detected"] = r["clean_result"]["oc_detected_clauses"]
        save_r["pert_oc_detected"] = r["pert_result"]["oc_detected_clauses"]
        save_r["pert_clause_details"] = r["pert_result"]["clause_details"]
        save_r["pert_conflict_fanout"] = r["pert_result"]["conflict_fanout"]
        save_results.append(save_r)

    out_path = RESULTS_DIR / "alphago_experiment.json"
    out_path.write_text(json.dumps(
        {"method": "alphago_mcgs", "results": save_results},
        indent=2, ensure_ascii=False, default=str,
    ))
    print(f"\nSaved to {out_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
