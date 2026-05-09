"""R6_CONFORMAL: Run Online Conformal MCGS on all 6 SCC cases.

SCC-only (skip DAG). Uses:
  - max_tokens=8192 + compact prompt (fix JSON truncation)
  - CVaR+EVT pruning (prevent SCC collapse)
  - Fixed dominance pruning (strict dominance with overall_risk_score fallback)
  - Online Conformal MCGS (self-calibrating risk detection)

Reuses R3_SCC direct LLM values for fair comparison.

Usage:
    python -m experiments.run_online_conformal
"""
from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.models.clause import ClauseEvaluation
from src.models.evaluation import ContractFinalResult
from src.models.graph import DependencyGraph
from src.modules.aggregator import Aggregator
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.pruning import DominancePruner, InfluencePruner
from src.modules.risk_identifier import RiskIdentifier
from src.modules.scc_sampler import SCCSampler
from src.modules.tarjan import TarjanSCCDetector

from experiments.perturbation import (
    perturb_type_a,
    perturb_type_b,
    perturb_type_c,
)
from experiments.runner import _extract_clause_metrics


def _prepare_graph(graph: DependencyGraph, config: dict) -> DependencyGraph:
    DomainGraphPruner(config).prune(graph)
    return TarjanSCCDetector().detect(graph)


def _make_dummy_dag_results(graph: DependencyGraph) -> dict[str, ClauseEvaluation]:
    scc_cids = set()
    for scc in graph.sccs:
        scc_cids.update(scc.clause_ids)
    return {
        cid: ClauseEvaluation(clause_id=cid, overall_risk_score=0.3, reasoning="DAG placeholder")
        for cid in graph.clauses if cid not in scc_cids
    }


async def run_one_case(
    graph: DependencyGraph,
    config: dict,
    llm_client,
    target_id: str,
    ptype: str,
    scc_node_ids: list[str],
    clause_y_id: str | None,
    baseline_risk: float,
    label: str,
) -> dict[str, Any]:
    if ptype == "type_a":
        pg = perturb_type_a(graph, target_id)
    elif ptype == "type_b":
        pg = perturb_type_b(graph, scc_node_ids, target_id, clause_y_id)
    elif ptype == "type_c":
        pg = perturb_type_c(graph, scc_node_ids, target_id)
    else:
        raise ValueError(f"Unknown ptype: {ptype}")

    pg = _prepare_graph(pg, config)
    dag_results = _make_dummy_dag_results(pg)

    enh_config = json.loads(json.dumps(config))
    enh_config["scc"]["num_samples"] = 8
    enh_config["mcgs"] = {
        **config.get("mcgs", {}),
        "num_rollouts": 20,
        "early_stopping": True,
        "convergence_window": 5,
        "convergence_threshold": 0.02,
    }
    enh_config.setdefault("pruning", {}).update({
        "cvar_alpha": 0.8,
        "cvar_safe_threshold": 0.4,
    })
    enh_config["detection"] = {
        "alpha": 0.1,
        "min_rollouts": 3,
        "confidence_delta": 0.05,
    }

    from src.modules.pruning.cvar_variance_pruner import CVaRVariancePruner
    from src.modules.online_conformal_mcgs import OnlineConformalMCGS

    sampler = SCCSampler(llm_client, enh_config)
    cvar_pruner = CVaRVariancePruner(enh_config)
    online_mcgs = OnlineConformalMCGS(enh_config)

    t0 = time.monotonic()

    if pg.sccs:
        logger.info(f"  [{label}] Sampling {len(pg.sccs)} SCCs...")
        scc_samples = await sampler.sample_all_sccs(pg, dag_results)
    else:
        scc_samples = {}

    cvar_pruner.prune(pg)

    search_tree = sampler.build_search_tree(pg, scc_samples)

    dom_pruner = DominancePruner(enh_config)
    dom_stats = dom_pruner.prune(search_tree)
    InfluencePruner(enh_config).prune(search_tree, pg)

    active = {sid: n for sid, n in search_tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())
    logger.info(f"  [{label}] After pruning: {len(active)} SCCs, {total_active} branches")

    if not active or total_active == 0:
        logger.warning(f"  [{label}] No active branches — MCGS cannot run")
        rollout_results: list[dict[str, Any]] = []
    else:
        logger.info(f"  [{label}] Running Online Conformal MCGS ({online_mcgs.num_rollouts} rollouts)...")
        rollout_results = online_mcgs.search(search_tree, dag_results, pg)

    collapsed_results = {}
    for scc in pg.sccs:
        if scc.is_collapsed and scc.collapsed_value:
            collapsed_results.update(scc.collapsed_value)

    aggregator = Aggregator(enh_config)
    result = aggregator.aggregate(rollout_results, dag_results, collapsed_results, pg)
    result.contract_id = label

    identifier = RiskIdentifier(enh_config)
    result = identifier.identify(result, pg)

    elapsed = time.monotonic() - t0

    metrics = _extract_clause_metrics(result, target_id)
    scc_stats = result.scc_statistics
    online_detected = target_id in online_mcgs.detected_clauses
    detected = metrics["high_risk"] or metrics["uncertain"] or online_detected

    logger.info(
        f"  [{label}] risk={metrics['risk_score']:.3f}, Δ={metrics['risk_score']-baseline_risk:+.3f}, "
        f"detected={'✓' if detected else '✗'}, online_conformal={'✓' if online_detected else '✗'}, "
        f"collapsed={scc_stats.get('collapsed_count',0)}/{scc_stats.get('num_sccs',0)}, "
        f"branches_kept={total_active}, rollouts={len(rollout_results)}, "
        f"time={elapsed:.0f}s"
    )
    if online_mcgs.detection_log:
        for entry in online_mcgs.detection_log:
            logger.info(
                f"    OC detected: {entry['clause_id']} at rollout {entry['detected_at_rollout']} "
                f"(z={entry['z_score']:.2f}, rank={entry['avg_rank']:.2f}, exc={entry['exceedance_frac']:.2f})"
            )

    return {
        "graph_id": "bgb_focus",
        "target_clause_id": target_id,
        "node_type": "scc",
        "scc_id": None,
        "perturbation_type": ptype,
        "mcgs_risk_score": metrics["risk_score"],
        "mcgs_max_risk": metrics["max_risk"],
        "mcgs_std": metrics["std"],
        "mcgs_reward_mean": 0.0,
        "mcgs_reward_std": 0.0,
        "mcgs_high_risk_detected": detected,
        "mcgs_uncertain_detected": metrics["uncertain"],
        "direct_llm_risk_score": 0.0,
        "direct_llm_detected": False,
        "mcgs_time_seconds": elapsed,
        "direct_llm_time_seconds": 0.0,
        "delta_mcgs_risk": metrics["risk_score"] - baseline_risk,
        "delta_mcgs_max": 0.0,
        "delta_mcgs_std": 0.0,
        "delta_direct_llm_risk": 0.0,
        "run_id": 1,
        "round": "R6_CONFORMAL",
        "config_name": "online_conformal",
        "online_conformal_detected": online_detected,
        "scc_collapsed": scc_stats.get("collapsed_count", 0),
        "branches_kept": total_active,
        "rollouts_run": len(rollout_results),
        "detection_log": [
            {k: round(v, 4) if isinstance(v, float) else v for k, v in e.items()}
            for e in online_mcgs.detection_log
        ],
    }


async def main():
    logger.info("=" * 70)
    logger.info("R6_CONFORMAL: Online Conformal MCGS on all 6 SCC cases")
    logger.info("=" * 70)

    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    from src.llm import OpenAIClient
    llm_client = OpenAIClient(config["llm"])

    from src.data.loader import QuantLawLoader
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/bgb_focus.gpickle.gz"
    )

    baseline = ContractFinalResult(**json.loads(
        Path("experiments/results/baseline_bgb_focus.json").read_text()
    ))

    targets = json.loads(Path("experiments/data/experiment_targets.json").read_text())
    scc_targets = targets["scc_targets"]

    # Load R3_SCC direct LLM data for fair comparison
    live_data = json.loads(Path("experiments/results/live_results.json").read_text())
    r3_llm = {}
    for r in live_data:
        if r.get("round") == "R3_SCC":
            key = (r["target_clause_id"], r["perturbation_type"])
            r3_llm[key] = {
                "direct_llm_risk_score": r["direct_llm_risk_score"],
                "direct_llm_detected": r["direct_llm_detected"],
                "delta_direct_llm_risk": r["delta_direct_llm_risk"],
                "direct_llm_time_seconds": r.get("direct_llm_time_seconds", 0),
            }

    jobs = []
    for scc in scc_targets:
        target_id = scc["node_ids"][0]
        clause_y_id = scc["node_ids"][1] if len(scc["node_ids"]) > 1 else None
        baseline_risk = _extract_clause_metrics(baseline, target_id)["risk_score"]
        for ptype in ["type_a", "type_b", "type_c"]:
            jobs.append({
                "target_id": target_id,
                "scc_node_ids": scc["node_ids"],
                "clause_y_id": clause_y_id,
                "ptype": ptype,
                "baseline_risk": baseline_risk,
            })

    logger.info(f"Total: {len(jobs)} SCC cases")

    results = []
    for i, job in enumerate(jobs):
        label = f"{job['target_id']}/{job['ptype']}"
        logger.info(f"\n{'='*60}")
        logger.info(f"[{i+1}/{len(jobs)}] {label}")
        logger.info(f"{'='*60}")

        try:
            r = await run_one_case(
                graph, config, llm_client,
                job["target_id"], job["ptype"],
                job["scc_node_ids"], job["clause_y_id"],
                job["baseline_risk"], label,
            )
            # Patch in R3_SCC direct LLM data
            key = (job["target_id"], job["ptype"])
            if key in r3_llm:
                r.update(r3_llm[key])
            results.append(r)
        except Exception as e:
            logger.error(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    logger.info("\n" + "=" * 100)
    logger.info("R6_CONFORMAL SUMMARY")
    logger.info("=" * 100)
    logger.info(f"  {'Target':<12} {'Type':<8} {'Risk':>6} {'Δ':>7} {'Det':>4} {'OC Det':>7} {'Branches':>9} {'Rolls':>6} {'Coll':>5}")
    logger.info("─" * 100)

    for r in results:
        det = "✓" if r["mcgs_high_risk_detected"] else "✗"
        oc = "✓" if r.get("online_conformal_detected") else "✗"
        logger.info(
            f"  {r['target_clause_id']:<12} {r['perturbation_type']:<8} "
            f"{r['mcgs_risk_score']:>6.3f} {r['delta_mcgs_risk']:>+7.3f} "
            f"{det:>4} {oc:>7} "
            f"{r.get('branches_kept', 0):>9} {r.get('rollouts_run', 0):>6} "
            f"{r.get('scc_collapsed', 0):>5}"
        )

    # Merge into live_results.json
    live_path = Path("experiments/results/live_results.json")
    existing = json.loads(live_path.read_text()) if live_path.exists() else []
    existing = [r for r in existing if r.get("round") != "R6_CONFORMAL"]
    clean_results = []
    for r in results:
        cr = {k: v for k, v in r.items() if k != "detection_log"}
        clean_results.append(cr)
    existing.extend(clean_results)
    live_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False, default=str))
    logger.info(f"\nMerged {len(results)} results into {live_path}")

    # Save standalone with detection logs
    standalone = Path("experiments/results/r6_conformal_results.json")
    standalone.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    logger.info(f"Full results (with detection logs) saved to {standalone}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
