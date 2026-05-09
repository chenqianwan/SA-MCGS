"""Compare Original vs Plan A vs Plan B on synthetic SCC data.

This experiment constructs synthetic SCC evaluation data that mimics the
real scenario: a few clauses in an SCC have injected risk (perturbation),
but the risk signal is diluted by healthy clauses.

We test whether each approach successfully detects the injected risk.

No LLM calls needed — all evaluation scores are synthetic.

Usage:
    python -m experiments.compare_plans
"""
from __future__ import annotations

import copy
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, stdev, variance

from loguru import logger

# ── Import the three approaches ──────────────────────────────────────

from src.models.clause import Clause, ClauseEvaluation, ClauseType, RiskDimension
from src.models.evaluation import ClauseFinalResult, ContractFinalResult
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo
from src.models.search_tree import SCCBranch, SearchTree, SearchTreeNode

from src.modules.pruning.variance_pruner import VariancePruner
from src.modules.pruning.cvar_variance_pruner import CVaRVariancePruner
from src.modules.mcgs import MCGS
from src.modules.cvar_mcgs import CVaRMCGS
from src.modules.online_conformal_mcgs import OnlineConformalMCGS
from src.modules.aggregator import Aggregator
from src.modules.conformal_risk import ConformalAggregator, ConformalRiskController


# ── Synthetic data generator ─────────────────────────────────────────

def make_clause(cid: str, title: str) -> Clause:
    return Clause(id=cid, title=title, content=f"Content of {title}",
                  clause_type=ClauseType.OBLIGATION)


def make_evaluation(cid: str, score: float, noise: float = 0.05) -> ClauseEvaluation:
    s = max(0.0, min(1.0, score + random.gauss(0, noise)))
    dims = [
        RiskDimension(name="financial_exposure", score=max(0, min(1, s + random.gauss(0, 0.03)))),
        RiskDimension(name="liability_scope", score=max(0, min(1, s + random.gauss(0, 0.03)))),
        RiskDimension(name="ambiguity", score=max(0, min(1, s * 0.8 + random.gauss(0, 0.03)))),
    ]
    return ClauseEvaluation(clause_id=cid, overall_risk_score=s, dimensions=dims,
                            reasoning=f"Synthetic eval score={s:.3f}")


def build_synthetic_scenario(
    n_dag: int = 15,
    scc_sizes: tuple[int, ...] = (5, 4),
    n_samples: int = 8,
    perturb_target: str | None = None,
    perturb_boost: float = 0.35,
    seed: int = 42,
) -> tuple[DependencyGraph, dict[str, ClauseEvaluation], dict[str, list], str]:
    """Build a synthetic graph with DAG + SCC nodes and generate samples.

    Returns (graph, dag_results, scc_samples_map, target_clause_id).
    """
    rng = random.Random(seed)
    random.seed(seed)

    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []

    # DAG nodes
    dag_ids = []
    for i in range(n_dag):
        cid = f"dag_{i}"
        clauses[cid] = make_clause(cid, f"§{i+1} DAG Clause")
        dag_ids.append(cid)
        if i > 0 and rng.random() < 0.5:
            edges.append(Edge(source=f"dag_{rng.randint(0, i-1)}", target=cid,
                              dependency_type=DependencyType.REFERENCES))

    # SCC groups
    scc_infos: list[SCCInfo] = []
    scc_all_ids: list[str] = []
    node_idx = n_dag
    for grp_idx, sz in enumerate(scc_sizes):
        scc_ids = []
        internal_edges = []
        for j in range(sz):
            cid = f"scc{grp_idx}_{j}"
            clauses[cid] = make_clause(cid, f"§{node_idx+1} SCC{grp_idx} Clause {j}")
            scc_ids.append(cid)
            node_idx += 1
        for j in range(sz):
            e = Edge(source=scc_ids[j], target=scc_ids[(j+1) % sz],
                     dependency_type=DependencyType.REFERENCES)
            edges.append(e)
            internal_edges.append(e)
        edges.append(Edge(source=dag_ids[rng.randint(0, n_dag-1)], target=scc_ids[0],
                          dependency_type=DependencyType.REFERENCES))

        scc_infos.append(SCCInfo(id=f"scc_{grp_idx}", clause_ids=scc_ids,
                                 internal_edges=internal_edges))
        scc_all_ids.extend(scc_ids)

    # Pick perturbation target
    target = perturb_target or scc_infos[0].clause_ids[0]

    graph = DependencyGraph(
        clauses=clauses, edges=edges, sccs=scc_infos,
        dag_nodes=dag_ids,
        topological_order=[{"id": f"scc_{i}", "type": "scc"} for i in range(len(scc_sizes))],
        metadata={"dag_ratio": n_dag / (n_dag + sum(scc_sizes))},
    )

    # DAG evaluations — low risk
    dag_results: dict[str, ClauseEvaluation] = {}
    for cid in dag_ids:
        dag_results[cid] = make_evaluation(cid, rng.uniform(0.1, 0.35), noise=0.04)

    # SCC samples — baseline (low risk, tight variance)
    for scc in graph.sccs:
        samples = []
        for s_idx in range(n_samples):
            evals = {}
            for cid in scc.clause_ids:
                base_score = 0.25 if cid != target else 0.25
                evals[cid] = make_evaluation(cid, base_score, noise=0.04)
            samples.append({"sample_id": s_idx, "evaluations": evals})
        scc.samples = samples
        scc.variance = _compute_scc_variance(samples)

    return graph, dag_results, {}, target


def build_perturbed_scenario(
    graph: DependencyGraph,
    dag_results: dict[str, ClauseEvaluation],
    target: str,
    perturb_boost: float = 0.35,
    n_samples: int = 8,
    seed: int = 123,
) -> DependencyGraph:
    """Clone graph and inject risk into target clause's SCC samples."""
    random.seed(seed)
    g2 = graph.model_copy(deep=True)

    for scc in g2.sccs:
        if target not in scc.clause_ids:
            continue
        samples = []
        for s_idx in range(n_samples):
            evals = {}
            for cid in scc.clause_ids:
                if cid == target:
                    score = 0.25 + perturb_boost + random.gauss(0, 0.06)
                else:
                    score = 0.25 + random.gauss(0, 0.04)
                evals[cid] = make_evaluation(cid, score, noise=0.02)
            samples.append({"sample_id": s_idx, "evaluations": evals})
        scc.samples = samples
        scc.variance = _compute_scc_variance(samples)

    return g2


def _compute_scc_variance(samples):
    if len(samples) < 2:
        return 0.0
    clause_ids = list(samples[0]["evaluations"].keys())
    variances = []
    for cid in clause_ids:
        scores = [s["evaluations"][cid].overall_risk_score for s in samples]
        variances.append(variance(scores) if len(scores) > 1 else 0.0)
    return sum(variances) / len(variances) if variances else 0.0


# ── Run pipeline for each approach ───────────────────────────────────

def build_search_tree(graph: DependencyGraph) -> SearchTree:
    """Build search tree from non-collapsed SCCs."""
    nodes = {}
    for scc in graph.sccs:
        if scc.is_collapsed:
            continue
        branches = []
        for sample in scc.samples:
            branches.append(SCCBranch(
                branch_id=f"{scc.id}_b{sample['sample_id']}",
                scc_id=scc.id,
                evaluation=sample["evaluations"],
            ))
        nodes[scc.id] = SearchTreeNode(scc_id=scc.id, branches=branches, depth=0)
    topo = [item["id"] for item in graph.topological_order if item["type"] == "scc"]
    return SearchTree(nodes=nodes, scc_topological_order=[s for s in topo if s in nodes])


def run_original(graph: DependencyGraph, dag_results: dict, config: dict) -> dict:
    """Original pipeline: VariancePruner + vanilla MCGS + fixed threshold Aggregator."""
    g = graph.model_copy(deep=True)

    pruner = VariancePruner(config)
    prune_stats = pruner.prune(g)

    tree = build_search_tree(g)
    mcgs = MCGS(config)
    active = {sid: n for sid, n in tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())

    if active and total_active > len(active):
        rollouts = mcgs.search(tree, dag_results, g)
    else:
        rollouts = []

    collapsed = {}
    for scc in g.sccs:
        if scc.is_collapsed and scc.collapsed_value:
            collapsed.update(scc.collapsed_value)

    aggregator = Aggregator(config)
    result = aggregator.aggregate(rollouts, dag_results, collapsed, g)

    return {
        "approach": "Original",
        "prune_stats": prune_stats,
        "num_rollouts": len(rollouts),
        "result": result,
    }


def run_plan_a(
    graph: DependencyGraph,
    dag_results: dict,
    config: dict,
    baseline_scores: list[float],
) -> dict:
    """Plan A: Original pruner/MCGS + Conformal Risk Control for detection."""
    g = graph.model_copy(deep=True)

    pruner = VariancePruner(config)
    prune_stats = pruner.prune(g)

    tree = build_search_tree(g)
    mcgs = MCGS(config)
    active = {sid: n for sid, n in tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())

    if active and total_active > len(active):
        rollouts = mcgs.search(tree, dag_results, g)
    else:
        rollouts = []

    collapsed = {}
    for scc in g.sccs:
        if scc.is_collapsed and scc.collapsed_value:
            collapsed.update(scc.collapsed_value)

    conf_agg = ConformalAggregator(config, baseline_scores=baseline_scores)
    aggregator = Aggregator(config)
    result = aggregator.aggregate(rollouts, dag_results, collapsed, g)

    # Override detection with conformal threshold
    conformal_high_risk = sorted(
        cid for cid, r in result.clause_results.items()
        if conf_agg.is_high_risk(r.max_risk_score)
    )
    result.high_risk_clauses = conformal_high_risk

    return {
        "approach": "Plan A (Conformal)",
        "conformal_threshold": conf_agg.high_risk_threshold,
        "prune_stats": prune_stats,
        "num_rollouts": len(rollouts),
        "result": result,
    }


def run_plan_b(graph: DependencyGraph, dag_results: dict, config: dict) -> dict:
    """Plan B: CVaR+EVT pruner + CVaR-MCGS + standard aggregator."""
    g = graph.model_copy(deep=True)

    pruner = CVaRVariancePruner(config)
    prune_stats = pruner.prune(g)

    tree = build_search_tree(g)
    mcgs = CVaRMCGS(config)
    active = {sid: n for sid, n in tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())

    if active and total_active > len(active):
        rollouts = mcgs.search(tree, dag_results, g)
    else:
        rollouts = []

    collapsed = {}
    for scc in g.sccs:
        if scc.is_collapsed and scc.collapsed_value:
            collapsed.update(scc.collapsed_value)

    aggregator = Aggregator(config)
    result = aggregator.aggregate(rollouts, dag_results, collapsed, g)

    return {
        "approach": "Plan B (CVaR+EVT)",
        "prune_stats": prune_stats,
        "num_rollouts": len(rollouts),
        "result": result,
    }


def run_online_conformal(graph: DependencyGraph, dag_results: dict, config: dict) -> dict:
    """Online Conformal: self-calibrating during MCGS search. No baseline needed."""
    g = graph.model_copy(deep=True)

    pruner = CVaRVariancePruner(config)
    prune_stats = pruner.prune(g)

    tree = build_search_tree(g)
    mcgs = OnlineConformalMCGS(config)
    active = {sid: n for sid, n in tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())

    if active and total_active > len(active):
        rollouts = mcgs.search(tree, dag_results, g)
    else:
        rollouts = []

    collapsed = {}
    for scc in g.sccs:
        if scc.is_collapsed and scc.collapsed_value:
            collapsed.update(scc.collapsed_value)

    aggregator = Aggregator(config)
    result = aggregator.aggregate(rollouts, dag_results, collapsed, g)

    # Online conformal detection overrides high_risk_clauses
    online_detected = mcgs.detected_clauses
    combined_high_risk = sorted(
        set(result.high_risk_clauses) | online_detected
    )
    result.high_risk_clauses = combined_high_risk

    return {
        "approach": "Online Conformal",
        "prune_stats": prune_stats,
        "num_rollouts": len(rollouts),
        "result": result,
        "online_detected": sorted(online_detected),
        "final_threshold": mcgs.running_threshold,
        "detection_log": mcgs.detection_log,
    }


# ── Main experiment ──────────────────────────────────────────────────

def run_experiment():
    logger.info("=" * 70)
    logger.info("Synthetic Comparison: Original vs Plan A vs Plan B")
    logger.info("=" * 70)

    config = {
        "pruning": {
            "variance_threshold": 0.001,
            "cvar_alpha": 0.8,
            "cvar_safe_threshold": 0.4,
            "influence_threshold": 0.3,
            "risk_dimensions": ["financial_exposure", "liability_scope", "ambiguity"],
        },
        "mcgs": {
            "num_rollouts": 50,
            "ucb_exploration_weight": 1.414,
            "early_stopping": True,
            "convergence_window": 8,
            "convergence_threshold": 0.015,
            "cvar_alpha": 0.8,
            "risk_lambda": 0.3,
            "lambda_lr": 0.05,
            "risk_budget": 0.5,
        },
        "aggregation": {
            "high_risk_threshold": 0.7,
            "high_uncertainty_threshold": 0.15,
            "conformal_alpha": 0.1,
        },
        "detection": {
            "alpha": 0.1,
            "min_rollouts": 3,
            "confidence_delta": 0.05,
        },
    }

    N_REPEATS = 5
    perturb_boosts = [0.10, 0.15, 0.20, 0.25, 0.35]

    all_results = []

    for boost in perturb_boosts:
        logger.info(f"\n{'─'*50}")
        logger.info(f"Perturbation boost = +{boost:.2f}")
        logger.info(f"{'─'*50}")

        for repeat in range(N_REPEATS):
            seed_base = repeat * 1000
            seed_perturb = repeat * 1000 + 500

            # Build baseline graph
            graph_base, dag_results, _, target = build_synthetic_scenario(
                n_dag=15, scc_sizes=(5, 4), n_samples=8, seed=seed_base
            )

            # Collect baseline scores for conformal calibration
            baseline_scores = []
            for scc in graph_base.sccs:
                for sample in scc.samples:
                    for ev in sample["evaluations"].values():
                        baseline_scores.append(ev.overall_risk_score)

            # Build perturbed graph
            graph_pert = build_perturbed_scenario(
                graph_base, dag_results, target,
                perturb_boost=boost, n_samples=8, seed=seed_perturb
            )

            # Run all four approaches on the PERTURBED graph
            res_orig = run_original(graph_pert, dag_results, config)
            res_a = run_plan_a(graph_pert, dag_results, config, baseline_scores)
            res_b = run_plan_b(graph_pert, dag_results, config)
            res_oc = run_online_conformal(graph_pert, dag_results, config)

            # Also run baseline for delta computation
            res_base = run_original(graph_base, dag_results, config)

            for label, res, base_res in [
                ("Original", res_orig, res_base),
                ("Plan A", res_a, res_base),
                ("Plan B", res_b, res_base),
                ("Online Conformal", res_oc, res_base),
            ]:
                result = res["result"]
                base_result = base_res["result"]

                target_cr = result.clause_results.get(target)
                target_base_cr = base_result.clause_results.get(target)

                target_score = target_cr.mean_risk_score if target_cr else 0.0
                target_max = target_cr.max_risk_score if target_cr else 0.0
                target_std = target_cr.std_risk_score if target_cr else 0.0
                base_score = target_base_cr.mean_risk_score if target_base_cr else 0.0

                delta = target_score - base_score
                detected_absolute = target in result.high_risk_clauses
                detected_uncertain = target in result.uncertain_clauses
                detected_delta = delta > 0.15

                collapsed_count = res["prune_stats"].get("collapsed", 0)
                total_sccs = res["prune_stats"].get("total_sccs", 0)

                row = {
                    "approach": res["approach"],
                    "boost": boost,
                    "repeat": repeat,
                    "target": target,
                    "target_mean_risk": round(target_score, 4),
                    "target_max_risk": round(target_max, 4),
                    "target_std": round(target_std, 4),
                    "baseline_mean_risk": round(base_score, 4),
                    "delta": round(delta, 4),
                    "detected_absolute": detected_absolute,
                    "detected_uncertain": detected_uncertain,
                    "detected_delta": detected_delta,
                    "detected_any": detected_absolute or detected_uncertain or detected_delta,
                    "collapsed": f"{collapsed_count}/{total_sccs}",
                    "num_rollouts": res["num_rollouts"],
                    "overall_risk": round(result.overall_risk_score, 4),
                }
                if "conformal_threshold" in res:
                    row["conformal_threshold"] = round(res["conformal_threshold"], 4)
                all_results.append(row)

    # ── Print summary table ──────────────────────────────────────────
    logger.info("\n" + "=" * 90)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 90)

    header = (
        f"{'Approach':<22} {'Boost':>5} "
        f"{'Target↑':>8} {'Base':>6} {'Δ':>7} "
        f"{'Det?':>5} {'Collapse':>9} {'Rollouts':>8} "
        f"{'Overall':>8}"
    )
    logger.info(header)
    logger.info("─" * 90)

    for r in all_results:
        det_mark = "✓" if r["detected_any"] else "✗"
        logger.info(
            f"{r['approach']:<22} {r['boost']:>5.2f} "
            f"{r['target_mean_risk']:>8.4f} {r['baseline_mean_risk']:>6.4f} {r['delta']:>+7.4f} "
            f"{det_mark:>5} {r['collapsed']:>9} {r['num_rollouts']:>8} "
            f"{r['overall_risk']:>8.4f}"
        )

    # ── Aggregate detection rates ────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("DETECTION RATES (across all repeats)")
    logger.info("=" * 70)

    from collections import defaultdict
    groups: dict[str, dict[float, list]] = defaultdict(lambda: defaultdict(list))
    for r in all_results:
        groups[r["approach"]][r["boost"]].append(r)

    header2 = f"{'Approach':<22} {'Boost':>5}  {'Abs%':>5} {'Δ%':>5} {'Any%':>5} {'AvgΔ':>7} {'AvgRollouts':>11}"
    logger.info(header2)
    logger.info("─" * 70)

    for approach in ["Original", "Plan A (Conformal)", "Plan B (CVaR+EVT)", "Online Conformal"]:
        for boost in perturb_boosts:
            rows = groups[approach][boost]
            n = len(rows)
            abs_rate = sum(r["detected_absolute"] for r in rows) / n * 100
            delta_rate = sum(r["detected_delta"] for r in rows) / n * 100
            any_rate = sum(r["detected_any"] for r in rows) / n * 100
            avg_delta = sum(r["delta"] for r in rows) / n
            avg_rollouts = sum(r["num_rollouts"] for r in rows) / n
            logger.info(
                f"{approach:<22} {boost:>5.2f}  {abs_rate:>4.0f}% {delta_rate:>4.0f}% "
                f"{any_rate:>4.0f}% {avg_delta:>+7.4f} {avg_rollouts:>11.1f}"
            )

    # Save results
    out_path = Path("experiments/results/plan_comparison.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))
    logger.info(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    run_experiment()
