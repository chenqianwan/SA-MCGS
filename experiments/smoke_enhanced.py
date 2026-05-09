"""Smoke test: SCC-only — Original vs Enhanced.

Skips DAG evaluation (uses neutral 0.3 placeholders for upstream context).
Only tests SCC sampling → pruning → MCGS → aggregation.

Validates that:
  1. max_tokens=8192 + compact prompt fixes JSON truncation for large SCCs
  2. CVaR+EVT pruning prevents premature SCC collapse
  3. Online Conformal MCGS detects injected risk

Usage:
    python -m experiments.smoke_enhanced
"""
from __future__ import annotations

import asyncio
import json
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
from src.modules.mcgs import MCGS
from src.modules.pruning import DominancePruner, InfluencePruner, VariancePruner
from src.modules.risk_identifier import RiskIdentifier
from src.modules.scc_sampler import SCCSampler
from src.modules.tarjan import TarjanSCCDetector

from experiments.perturbation import perturb_type_a, _ensure_clause_text
from experiments.runner import _extract_clause_metrics


def _prepare_graph(graph: DependencyGraph, config: dict) -> DependencyGraph:
    """Run Step 3-4: graph pruning + Tarjan SCC detection."""
    pruner = DomainGraphPruner(config)
    pruner.prune(graph)
    tarjan = TarjanSCCDetector()
    graph = tarjan.detect(graph)
    return graph


def _make_dummy_dag_results(
    graph: DependencyGraph,
) -> dict[str, ClauseEvaluation]:
    """Neutral DAG results — only for upstream context, not tested."""
    scc_clause_ids = set()
    for scc in graph.sccs:
        scc_clause_ids.update(scc.clause_ids)

    results: dict[str, ClauseEvaluation] = {}
    for cid in graph.clauses:
        if cid not in scc_clause_ids:
            results[cid] = ClauseEvaluation(
                clause_id=cid,
                overall_risk_score=0.3,
                reasoning="DAG placeholder (smoke: SCC-only test)",
            )
    return results


async def _run_scc_pipeline(
    graph: DependencyGraph,
    dag_results: dict[str, ClauseEvaluation],
    scc_sampler: SCCSampler,
    variance_pruner,
    mcgs_engine,
    config: dict,
    label: str,
) -> tuple[ContractFinalResult, float]:
    """Run SCC sampling → pruning → MCGS → aggregation. Return (result, elapsed)."""
    t0 = time.monotonic()

    if graph.sccs:
        logger.info(f"[{label}] Sampling {len(graph.sccs)} SCCs...")
        scc_samples = await scc_sampler.sample_all_sccs(graph, dag_results)
    else:
        scc_samples = {}

    logger.info(f"[{label}] Variance pruning...")
    variance_pruner.prune(graph)

    logger.info(f"[{label}] Building search tree...")
    search_tree = scc_sampler.build_search_tree(graph, scc_samples)

    dominance = DominancePruner(config)
    influence = InfluencePruner(config)
    dominance.prune(search_tree)
    influence.prune(search_tree, graph)

    active_nodes = {
        sid: n for sid, n in search_tree.nodes.items() if n.active_branches
    }
    total_active = sum(len(n.active_branches) for n in active_nodes.values())
    logger.info(f"[{label}] Active: {len(active_nodes)} SCCs, {total_active} branches")

    if not active_nodes or total_active <= len(active_nodes):
        logger.info(f"[{label}] No MCGS needed — all SCCs resolved by pruning")
        rollout_results: list[dict[str, Any]] = []
    else:
        logger.info(f"[{label}] Running MCGS...")
        rollout_results = mcgs_engine.search(search_tree, dag_results, graph)

    collapsed_results = {}
    for scc in graph.sccs:
        if scc.is_collapsed and scc.collapsed_value:
            collapsed_results.update(scc.collapsed_value)

    aggregator = Aggregator(config)
    result = aggregator.aggregate(rollout_results, dag_results, collapsed_results, graph)
    result.contract_id = label

    identifier = RiskIdentifier(config)
    result = identifier.identify(result, graph)

    elapsed = time.monotonic() - t0
    return result, elapsed


async def main():
    logger.info("=" * 60)
    logger.info("SMOKE SCC-ONLY: bgb_275 type_a — Original vs Enhanced")
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

    baseline = ContractFinalResult(**json.loads(
        Path("experiments/results/baseline_bgb_focus.json").read_text()
    ))
    baseline_risk = _extract_clause_metrics(baseline, "bgb_275")["risk_score"]
    logger.info(f"Baseline bgb_275 risk: {baseline_risk}")

    target = "bgb_275"

    # ── Run 1: Original pipeline (SCC only) ──────────────────────
    logger.info("\n--- [1/2] ORIGINAL (SCC only) ---")
    pg1 = perturb_type_a(graph, target)
    pg1 = _prepare_graph(pg1, config)
    dag1 = _make_dummy_dag_results(pg1)

    scc_info = [s for s in pg1.sccs if target in s.clause_ids]
    logger.info(f"  Target SCC: {scc_info[0].id if scc_info else 'NOT FOUND'}, "
                f"size={len(scc_info[0].clause_ids) if scc_info else 0}")

    sampler_orig = SCCSampler(llm_client, config)
    pruner_orig = VariancePruner(config)
    mcgs_orig = MCGS(config)

    res_orig, t_orig = await _run_scc_pipeline(
        pg1, dag1, sampler_orig, pruner_orig, mcgs_orig, config, "ORIGINAL"
    )
    m_orig = _extract_clause_metrics(res_orig, target)
    scc_orig = res_orig.scc_statistics

    logger.info(f"  risk={m_orig['risk_score']:.3f}, max={m_orig['max_risk']:.3f}, "
                f"std={m_orig['std']:.3f}")
    logger.info(f"  Δ={m_orig['risk_score'] - baseline_risk:+.3f}")
    logger.info(f"  high_risk={m_orig['high_risk']}, uncertain={m_orig['uncertain']}")
    logger.info(f"  collapsed={scc_orig.get('collapsed_count', 0)}/{scc_orig.get('num_sccs', 0)}")
    logger.info(f"  rollouts={res_orig.search_statistics.get('num_rollouts', 0)}")
    logger.info(f"  time={t_orig:.0f}s")

    # ── Run 2: Enhanced pipeline (SCC only) ──────────────────────
    logger.info("\n--- [2/2] ENHANCED (CVaR+EVT + OnlineConformal, SCC only) ---")
    pg2 = perturb_type_a(graph, target)
    pg2 = _prepare_graph(pg2, config)
    dag2 = _make_dummy_dag_results(pg2)

    enh_config = json.loads(json.dumps(config))
    enh_config["scc"]["num_samples"] = 8
    enh_config["mcgs"]["num_rollouts"] = 20
    enh_config.setdefault("pruning", {}).update({
        "cvar_alpha": 0.8,
        "cvar_safe_threshold": 0.4,
    })
    enh_config["detection"] = {
        "alpha": 0.1, "min_rollouts": 3, "confidence_delta": 0.05,
    }

    from src.modules.pruning.cvar_variance_pruner import CVaRVariancePruner
    from src.modules.online_conformal_mcgs import OnlineConformalMCGS

    sampler_enh = SCCSampler(llm_client, enh_config)
    pruner_enh = CVaRVariancePruner(enh_config)
    online_mcgs = OnlineConformalMCGS(enh_config)

    res_enh, t_enh = await _run_scc_pipeline(
        pg2, dag2, sampler_enh, pruner_enh, online_mcgs, enh_config, "ENHANCED"
    )
    m_enh = _extract_clause_metrics(res_enh, target)
    scc_enh = res_enh.scc_statistics
    online_detected = target in online_mcgs.detected_clauses

    logger.info(f"  risk={m_enh['risk_score']:.3f}, max={m_enh['max_risk']:.3f}, "
                f"std={m_enh['std']:.3f}")
    logger.info(f"  Δ={m_enh['risk_score'] - baseline_risk:+.3f}")
    logger.info(f"  high_risk={m_enh['high_risk']}, uncertain={m_enh['uncertain']}")
    logger.info(f"  online_conformal_detected={online_detected}")
    logger.info(f"  collapsed={scc_enh.get('collapsed_count', 0)}/{scc_enh.get('num_sccs', 0)}")
    logger.info(f"  rollouts={res_enh.search_statistics.get('num_rollouts', 0)}")
    logger.info(f"  time={t_enh:.0f}s")
    if online_mcgs.detection_log:
        logger.info(f"  detection_log={online_mcgs.detection_log}")

    # ── Summary ──────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("SMOKE SCC-ONLY RESULT: bgb_275 type_a")
    logger.info("=" * 60)

    orig_det = m_orig['high_risk'] or m_orig['uncertain']
    enh_det = m_enh['high_risk'] or m_enh['uncertain'] or online_detected

    logger.info(f"  {'':30} {'Original':>12} {'Enhanced':>12}")
    logger.info(f"  {'Risk score':30} {m_orig['risk_score']:>12.3f} {m_enh['risk_score']:>12.3f}")
    logger.info(f"  {'Max risk':30} {m_orig['max_risk']:>12.3f} {m_enh['max_risk']:>12.3f}")
    logger.info(f"  {'Std':30} {m_orig['std']:>12.3f} {m_enh['std']:>12.3f}")
    logger.info(f"  {'Delta vs baseline':30} {m_orig['risk_score']-baseline_risk:>+12.3f} {m_enh['risk_score']-baseline_risk:>+12.3f}")
    logger.info(f"  {'Detected?':30} {'✓' if orig_det else '✗':>12} {'✓' if enh_det else '✗':>12}")
    logger.info(f"  {'SCC collapsed':30} {scc_orig.get('collapsed_count',0):>12} {scc_enh.get('collapsed_count',0):>12}")
    logger.info(f"  {'Rollouts':30} {res_orig.search_statistics.get('num_rollouts',0):>12} {res_enh.search_statistics.get('num_rollouts',0):>12}")
    logger.info(f"  {'Time (s)':30} {t_orig:>12.0f} {t_enh:>12.0f}")
    logger.info(f"  {'Online conformal detected':30} {'N/A':>12} {'✓' if online_detected else '✗':>12}")

    verdict = (
        "PASS ✓ (Enhanced detects, Original misses)"
        if enh_det and not orig_det
        else "BOTH PASS" if enh_det and orig_det
        else "BOTH FAIL ✗" if not enh_det and not orig_det
        else "REGRESSION ✗"
    )
    logger.info(f"\n  Verdict: {verdict}")
    logger.info("=" * 60)

    out = {
        "target": target, "ptype": "type_a", "baseline_risk": baseline_risk,
        "scc_only": True,
        "original": {
            **m_orig,
            "collapsed": scc_orig.get("collapsed_count", 0),
            "rollouts": res_orig.search_statistics.get("num_rollouts", 0),
            "time": t_orig,
        },
        "enhanced": {
            **m_enh,
            "collapsed": scc_enh.get("collapsed_count", 0),
            "rollouts": res_enh.search_statistics.get("num_rollouts", 0),
            "time": t_enh,
            "online_detected": online_detected,
            "detection_log": online_mcgs.detection_log,
        },
    }
    Path("experiments/results/smoke_enhanced.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str)
    )

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
