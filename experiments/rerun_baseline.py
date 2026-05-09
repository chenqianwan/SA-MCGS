"""Rerun baseline for SCC clauses only (fix max_tokens issue).

The original baseline had max_tokens=4096 which caused JSON truncation
for large SCCs, resulting in fallback scores. This script:
  1. Loads the existing baseline (DAG results are correct)
  2. Re-evaluates only the SCC clauses with fixed config (max_tokens=8192 + compact)
  3. Saves the corrected baseline
  4. Recalculates deltas for R5_ENHANCED and R6_CONFORMAL

Usage:
    python -m experiments.rerun_baseline
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import yaml
from loguru import logger

from src.models.clause import ClauseEvaluation
from src.models.evaluation import ContractFinalResult
from src.models.graph import DependencyGraph
from src.modules.aggregator import Aggregator
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.pruning import DominancePruner, InfluencePruner, VariancePruner
from src.modules.mcgs import MCGS
from src.modules.risk_identifier import RiskIdentifier
from src.modules.scc_sampler import SCCSampler
from src.modules.tarjan import TarjanSCCDetector


async def main():
    logger.info("=" * 60)
    logger.info("RERUN BASELINE: Fix SCC scores (max_tokens=8192)")
    logger.info("=" * 60)

    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    from src.llm import OpenAIClient
    llm_client = OpenAIClient(config["llm"])

    from src.data.loader import QuantLawLoader
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/bgb_focus.gpickle.gz"
    )

    # Load existing baseline
    baseline_path = Path("experiments/results/baseline_bgb_focus.json")
    old_baseline = ContractFinalResult(**json.loads(baseline_path.read_text()))

    # Show old SCC scores
    logger.info("\n--- OLD BASELINE (affected by max_tokens bug) ---")
    scc_clauses_old = {
        cid: r for cid, r in old_baseline.clause_results.items()
        if r.source and 'scc' in r.source.lower()
    }
    for cid, r in sorted(scc_clauses_old.items()):
        logger.info(f"  {cid}: risk={r.mean_risk_score:.3f}, source={r.source}")
    logger.info(f"  Total SCC clauses: {len(scc_clauses_old)}")

    # Prepare graph
    DomainGraphPruner(config).prune(graph)
    graph = TarjanSCCDetector().detect(graph)
    logger.info(f"  SCCs: {len(graph.sccs)}, DAG nodes: {len(graph.clauses) - sum(len(s.clause_ids) for s in graph.sccs)}")

    # Extract DAG results from old baseline (these are correct)
    scc_cids = set()
    for scc in graph.sccs:
        scc_cids.update(scc.clause_ids)

    dag_results: dict[str, ClauseEvaluation] = {}
    for cid, r in old_baseline.clause_results.items():
        if cid not in scc_cids:
            dag_results[cid] = ClauseEvaluation(
                clause_id=cid,
                overall_risk_score=r.mean_risk_score,
                dimensions=[],
                reasoning=f"DAG baseline (original, correct)",
            )
    logger.info(f"  Reusing {len(dag_results)} DAG results from original baseline")

    # Re-run SCC sampling with fixed config
    logger.info("\n--- RE-RUNNING SCC SAMPLING (max_tokens=8192, compact) ---")
    t0 = time.monotonic()

    sampler = SCCSampler(llm_client, config)
    scc_samples = await sampler.sample_all_sccs(graph, dag_results)

    # Standard pruning (original algorithm, not CVaR+EVT)
    variance_pruner = VariancePruner(config)
    variance_pruner.prune(graph)

    search_tree = sampler.build_search_tree(graph, scc_samples)
    DominancePruner(config).prune(search_tree)
    InfluencePruner(config).prune(search_tree, graph)

    active = {sid: n for sid, n in search_tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())
    logger.info(f"  Active: {len(active)} SCCs, {total_active} branches")

    if not active or total_active == 0:
        rollout_results = []
    else:
        mcgs = MCGS(config)
        logger.info(f"  Running MCGS ({mcgs.num_rollouts} rollouts)...")
        rollout_results = mcgs.search(search_tree, dag_results, graph)

    collapsed_results = {}
    for scc in graph.sccs:
        if scc.is_collapsed and scc.collapsed_value:
            collapsed_results.update(scc.collapsed_value)

    aggregator = Aggregator(config)
    result = aggregator.aggregate(rollout_results, dag_results, collapsed_results, graph)
    result.contract_id = "bgb_focus_baseline"

    identifier = RiskIdentifier(config)
    result = identifier.identify(result, graph)

    elapsed = time.monotonic() - t0
    logger.info(f"  Baseline re-run complete in {elapsed:.0f}s")

    # Show new SCC scores
    logger.info("\n--- NEW BASELINE (fixed) ---")
    for cid in sorted(scc_cids):
        r_new = result.clause_results.get(cid)
        r_old = old_baseline.clause_results.get(cid)
        if r_new:
            old_risk = r_old.mean_risk_score if r_old else 0
            logger.info(
                f"  {cid}: risk={r_new.mean_risk_score:.3f} "
                f"(was {old_risk:.3f}, change={r_new.mean_risk_score - old_risk:+.3f})"
            )

    # Save corrected baseline
    backup_path = Path("experiments/results/baseline_bgb_focus_old_broken.json")
    if not backup_path.exists():
        backup_path.write_text(baseline_path.read_text())
        logger.info(f"  Backed up old baseline to {backup_path}")

    baseline_path.write_text(json.dumps(result.dict(), indent=2, ensure_ascii=False, default=str))
    logger.info(f"  Saved corrected baseline to {baseline_path}")

    # Recalculate deltas for R5_ENHANCED and R6_CONFORMAL
    logger.info("\n--- RECALCULATING DELTAS ---")
    live_path = Path("experiments/results/live_results.json")
    live_data = json.loads(live_path.read_text())

    updated = 0
    for r in live_data:
        target = r.get("target_clause_id")
        if not target:
            continue
        new_cr = result.clause_results.get(target)
        if not new_cr:
            continue
        new_baseline_risk = new_cr.mean_risk_score

        if r.get("round") in ("R5_ENHANCED", "R6_CONFORMAL"):
            old_delta = r.get("delta_mcgs_risk", 0)
            new_delta = (r.get("mcgs_risk_score", 0)) - new_baseline_risk
            r["delta_mcgs_risk"] = new_delta
            updated += 1
            logger.info(
                f"  {r['round']} {target}/{r['perturbation_type']}: "
                f"baseline {new_baseline_risk:.3f}, "
                f"delta {old_delta:+.3f} -> {new_delta:+.3f}"
            )

        # Also update R3_SCC deltas
        if r.get("round") == "R3_SCC":
            old_delta = r.get("delta_mcgs_risk", 0)
            new_delta = (r.get("mcgs_risk_score", 0)) - new_baseline_risk
            r["delta_mcgs_risk"] = new_delta
            updated += 1
            logger.info(
                f"  {r['round']} {target}/{r['perturbation_type']}: "
                f"baseline {new_baseline_risk:.3f}, "
                f"delta {old_delta:+.3f} -> {new_delta:+.3f}"
            )

    live_path.write_text(json.dumps(live_data, indent=2, ensure_ascii=False, default=str))
    logger.info(f"\n  Updated {updated} entries in {live_path}")

    # Summary comparison
    logger.info("\n" + "=" * 70)
    logger.info("BASELINE COMPARISON: Old (broken) vs New (fixed)")
    logger.info("=" * 70)
    logger.info(f"  {'Clause':<12} {'Old':>8} {'New':>8} {'Change':>8}")
    logger.info("  " + "-" * 40)
    for cid in sorted(scc_cids):
        old_r = old_baseline.clause_results.get(cid)
        new_r = result.clause_results.get(cid)
        old_v = old_r.mean_risk_score if old_r else 0
        new_v = new_r.mean_risk_score if new_r else 0
        logger.info(f"  {cid:<12} {old_v:>8.3f} {new_v:>8.3f} {new_v-old_v:>+8.3f}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
