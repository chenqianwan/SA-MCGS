"""MCGS vs Joint LLM: head-to-head on Type B & C perturbations.

For each real SCC in the 2019 BGB graph (various sizes 3-24 nodes):
  1. Apply Type B or Type C perturbation
  2. Run Joint LLM (single call, temp=0) → detect?
  3. Run MCGS (Online Conformal, 5 samples + search) → detect?
  4. Record and compare

This demonstrates MCGS's advantage on structural/subtle defects.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.models.clause import ClauseEvaluation
from src.models.graph import DependencyGraph
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.scc_sampler import SCCSampler
from src.modules.aggregator import Aggregator
from src.modules.risk_identifier import RiskIdentifier
from src.modules.pruning import DominancePruner, InfluencePruner

from experiments.perturbation import perturb_type_b, perturb_type_c

HIGH_RISK_THRESHOLD = 0.7


def _prepare_graph(graph: DependencyGraph, config: dict) -> DependencyGraph:
    DomainGraphPruner(config).prune(graph)
    return TarjanSCCDetector().detect(graph)


def _make_dummy_dag(graph: DependencyGraph) -> dict[str, ClauseEvaluation]:
    scc_cids = set()
    for scc in graph.sccs:
        scc_cids.update(scc.clause_ids)
    return {
        cid: ClauseEvaluation(clause_id=cid, overall_risk_score=0.3, reasoning="DAG placeholder")
        for cid in graph.clauses if cid not in scc_cids
    }


async def run_joint_llm(llm_client, perturbed_graph, scc_info, target_id, sampler):
    """Single Joint LLM call on the full SCC (temp=0)."""
    clauses = [perturbed_graph.clauses[cid] for cid in scc_info.clause_ids]
    use_compact = len(clauses) >= sampler.compact_threshold
    prompt = sampler._build_joint_prompt(clauses, scc_info.internal_edges, [], compact=use_compact)

    t0 = time.monotonic()
    try:
        resp = await llm_client.call_json(prompt, temperature=0.0, max_tokens=sampler.max_tokens)
        elapsed = time.monotonic() - t0
        evals = sampler._parse_joint_evaluation(resp, scc_info.clause_ids, compact=use_compact)
        target_eval = evals.get(target_id)
        if target_eval:
            score = target_eval.overall_risk_score
        else:
            score = 0.0
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.warning(f"Joint LLM failed: {e}")
        score = 0.0

    return score, score >= HIGH_RISK_THRESHOLD, elapsed


async def run_mcgs_conformal(llm_client, graph_original, config, target_id, ptype,
                              scc_node_ids, clause_y_id):
    """MCGS pipeline on just the target SCC (not the full graph)."""
    from src.models.graph import DependencyGraph, SCCInfo, Edge
    from src.modules.pruning.cvar_variance_pruner import CVaRVariancePruner
    from src.modules.online_conformal_mcgs import OnlineConformalMCGS

    if ptype == "type_b":
        pg = perturb_type_b(graph_original, scc_node_ids, target_id, clause_y_id)
    elif ptype == "type_c":
        pg = perturb_type_c(graph_original, scc_node_ids, target_id)
    else:
        raise ValueError(f"Unknown ptype: {ptype}")

    # Build a minimal subgraph containing ONLY the target SCC
    scc_set = set(scc_node_ids)
    sub_clauses = {cid: pg.clauses[cid] for cid in scc_node_ids if cid in pg.clauses}
    sub_edges = [e for e in pg.edges if e.source in scc_set and e.target in scc_set]

    sub_graph = DependencyGraph(
        contract_id="sub_scc",
        clauses=sub_clauses,
        edges=sub_edges,
        topological_order=[{"id": "scc_target", "type": "scc"}],
    )

    # Manually set up the SCC
    scc_info = SCCInfo(
        id="scc_target",
        clause_ids=list(scc_node_ids),
        internal_edges=sub_edges,
        is_collapsed=False,
    )
    sub_graph.sccs = [scc_info]

    dag_results = {}

    enh_config = json.loads(json.dumps(config))
    enh_config["scc"]["num_samples"] = 5
    enh_config["mcgs"] = {
        **config.get("mcgs", {}),
        "num_rollouts": 15,
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

    sampler = SCCSampler(llm_client, enh_config)
    online_mcgs = OnlineConformalMCGS(enh_config)

    t0 = time.monotonic()

    scc_samples = await sampler.sample_all_sccs(sub_graph, dag_results)

    search_tree = sampler.build_search_tree(sub_graph, scc_samples)

    dom_pruner = DominancePruner(enh_config)
    dom_pruner.prune(search_tree)

    active = {sid: n for sid, n in search_tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())

    if not active or total_active == 0:
        rollout_results = []
    else:
        rollout_results = online_mcgs.search(search_tree, dag_results, sub_graph)

    collapsed_results = {}
    for scc in sub_graph.sccs:
        if scc.is_collapsed and scc.collapsed_value:
            collapsed_results.update(scc.collapsed_value)

    aggregator = Aggregator(enh_config)
    result = aggregator.aggregate(rollout_results, dag_results, collapsed_results, sub_graph)
    identifier = RiskIdentifier(enh_config)
    result = identifier.identify(result, sub_graph)

    elapsed = time.monotonic() - t0

    cr = result.clause_results.get(target_id)
    if cr:
        score = cr.mean_risk_score
    else:
        score = 0.0

    online_detected = target_id in online_mcgs.detected_clauses
    high_risk = target_id in result.high_risk_clauses
    uncertain = target_id in result.uncertain_clauses
    detected = high_risk or uncertain or online_detected

    return score, detected, elapsed, online_detected, high_risk, uncertain, len(rollout_results)


async def main():
    logger.info("=" * 70)
    logger.info("MCGS vs Joint LLM: Type B & C on Real SCCs (2019 BGB)")
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

    # Select SCCs with mutual edges (needed for type_b)
    test_sccs = []
    for scc in sorted(graph.sccs, key=lambda s: -len(s.clause_ids)):
        if len(scc.clause_ids) < 3:
            continue
        edge_pairs = set()
        for e in scc.internal_edges:
            edge_pairs.add((e.source, e.target))
        mutual = [(a, b) for a, b in edge_pairs if (b, a) in edge_pairs]
        if not mutual:
            continue
        target_id = mutual[0][0]
        clause_y = mutual[0][1]
        total_chars = sum(len(graph.clauses[cid].content or '') for cid in scc.clause_ids)
        test_sccs.append({
            "scc": scc,
            "target_id": target_id,
            "clause_y": clause_y,
            "size": len(scc.clause_ids),
            "tokens": total_chars // 3,
        })

    logger.info(f"Selected {len(test_sccs)} SCCs for testing")
    for t in test_sccs:
        logger.info(f"  {t['size']} nodes, ~{t['tokens']} tokens, target={t['target_id']}, pair={t['clause_y']}")

    sampler = SCCSampler(llm_client, config)
    all_results = []

    for ptype in ["type_b", "type_c"]:
        logger.info(f"\n{'#'*70}")
        logger.info(f"PERTURBATION: {ptype}")
        logger.info(f"{'#'*70}")

        for t_info in test_sccs:
            scc = t_info["scc"]
            target_id = t_info["target_id"]
            clause_y = t_info["clause_y"]
            size = t_info["size"]
            tokens = t_info["tokens"]

            label = f"{target_id}/{ptype} ({size}n, ~{tokens}tok)"
            logger.info(f"\n{'='*60}")
            logger.info(f"{label}")
            logger.info(f"{'='*60}")

            # 1. Joint LLM
            logger.info(f"  [Joint LLM] Running...")
            if ptype == "type_b":
                pg_joint = perturb_type_b(graph, scc.clause_ids, target_id, clause_y)
            else:
                pg_joint = perturb_type_c(graph, scc.clause_ids, target_id)
            pg_joint = _prepare_graph(pg_joint, config)

            scc_info_joint = None
            for s in pg_joint.sccs:
                if target_id in s.clause_ids:
                    scc_info_joint = s
                    break

            if scc_info_joint:
                j_score, j_det, j_time = await run_joint_llm(
                    llm_client, pg_joint, scc_info_joint, target_id, sampler
                )
            else:
                j_score, j_det, j_time = 0.0, False, 0.0

            logger.info(
                f"  [Joint LLM] score={j_score:.3f}, detected={'YES' if j_det else 'NO'}, time={j_time:.1f}s"
            )

            # 2. MCGS (Online Conformal)
            logger.info(f"  [MCGS] Running...")
            try:
                m_score, m_det, m_time, m_oc, m_hr, m_unc, m_rolls = await run_mcgs_conformal(
                    llm_client, graph, config, target_id, ptype,
                    scc.clause_ids, clause_y
                )
                logger.info(
                    f"  [MCGS] score={m_score:.3f}, detected={'YES' if m_det else 'NO'}, "
                    f"HR={'YES' if m_hr else 'NO'}, UNC={'YES' if m_unc else 'NO'}, "
                    f"OC={'YES' if m_oc else 'NO'}, rollouts={m_rolls}, time={m_time:.1f}s"
                )
            except Exception as e:
                logger.error(f"  [MCGS] FAILED: {e}")
                import traceback; traceback.print_exc()
                m_score, m_det, m_time, m_oc, m_hr, m_unc, m_rolls = 0.0, False, 0.0, False, False, False, 0

            result = {
                "scc_size": size,
                "scc_tokens": tokens,
                "target_id": target_id,
                "perturbation": ptype,
                "joint_score": j_score,
                "joint_detected": j_det,
                "joint_time": j_time,
                "mcgs_score": m_score,
                "mcgs_detected": m_det,
                "mcgs_hr_detected": m_hr,
                "mcgs_unc_detected": m_unc,
                "mcgs_oc_detected": m_oc,
                "mcgs_rollouts": m_rolls,
                "mcgs_time": m_time,
            }
            all_results.append(result)

    # Save results
    output_path = Path("experiments/results/mcgs_vs_joint.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build summary
    summary_b = []
    summary_c = []
    for ptype, summary_list in [("type_b", summary_b), ("type_c", summary_c)]:
        ptype_results = [r for r in all_results if r["perturbation"] == ptype]
        for r in ptype_results:
            summary_list.append(r)

    output_data = {
        "experiment": "mcgs_vs_joint",
        "description": "MCGS (Online Conformal) vs Joint LLM on Type B & C perturbations",
        "type_b": summary_b,
        "type_c": summary_c,
        "all": all_results,
    }
    output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False))
    logger.info(f"\nResults saved to {output_path}")

    # Print summary table
    logger.info("\n" + "=" * 100)
    logger.info("FINAL COMPARISON: MCGS vs Joint LLM")
    logger.info("=" * 100)
    logger.info(
        f"{'Type':<8} {'Size':>5} {'Tokens':>7} {'Target':<14} "
        f"{'Joint':>6} {'J.Det':>6} {'MCGS':>6} {'M.Det':>6} {'OC':>4} {'Winner':>10}"
    )
    logger.info("-" * 100)
    for r in all_results:
        winner = "MCGS" if r["mcgs_detected"] and not r["joint_detected"] else \
                 "Both" if r["mcgs_detected"] and r["joint_detected"] else \
                 "Joint" if r["joint_detected"] and not r["mcgs_detected"] else \
                 "Neither"
        logger.info(
            f"{r['perturbation']:<8} {r['scc_size']:>5} {r['scc_tokens']:>7} {r['target_id']:<14} "
            f"{r['joint_score']:>6.3f} {'Y' if r['joint_detected'] else 'N':>6} "
            f"{r['mcgs_score']:>6.3f} {'Y' if r['mcgs_detected'] else 'N':>6} "
            f"{'Y' if r['mcgs_oc_detected'] else 'N':>4} "
            f"{winner:>10}"
        )

    # Aggregate stats
    for ptype in ["type_b", "type_c"]:
        pr = [r for r in all_results if r["perturbation"] == ptype]
        if not pr:
            continue
        j_det_rate = sum(1 for r in pr if r["joint_detected"]) / len(pr)
        m_det_rate = sum(1 for r in pr if r["mcgs_detected"]) / len(pr)
        logger.info(f"\n  {ptype}: Joint={j_det_rate:.0%}, MCGS={m_det_rate:.0%} ({len(pr)} cases)")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
