"""Deep experiment: 5-node Type C cases with enhanced MCGS parameters.

Parallelization strategy:
  - Both 5n cases (bgb_234, bgb_555c) run concurrently
  - For each case: Joint LLM (5 parallel trials) and MCGS run concurrently
  - Within MCGS: num_samples=10 initial LLM calls run in parallel (asyncio.gather)
  - MCGS rollouts (50) are essentially free (no LLM calls, pure UCB selection)

MCGS enhancements vs previous experiment:
  - num_samples: 5 → 10  (richer search tree)
  - num_rollouts: 10 → 50 (stronger statistical signal)
  - early_stopping: disabled (let all rollouts complete)
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
from src.models.clause import ClauseEvaluation
from src.models.graph import DependencyGraph, SCCInfo, Edge
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.scc_sampler import SCCSampler
from src.modules.aggregator import Aggregator
from src.modules.risk_identifier import RiskIdentifier
from src.modules.pruning import DominancePruner
from src.modules.online_conformal_mcgs import OnlineConformalMCGS

from experiments.perturbation import perturb_type_c

HIGH_RISK_THRESHOLD = 0.7


def _prepare_graph(graph: DependencyGraph, config: dict) -> DependencyGraph:
    DomainGraphPruner(config).prune(graph)
    return TarjanSCCDetector().detect(graph)


async def run_joint_llm_single(llm_client, perturbed_graph, scc_info, target_id, sampler, trial_id):
    """Single Joint LLM trial."""
    clauses = [perturbed_graph.clauses[cid] for cid in scc_info.clause_ids]
    use_compact = len(clauses) >= sampler.compact_threshold
    prompt = sampler._build_joint_prompt(clauses, scc_info.internal_edges, [], compact=use_compact)

    t0 = time.monotonic()
    try:
        resp = await llm_client.call_json(prompt, temperature=0.0, max_tokens=sampler.max_tokens)
        elapsed = time.monotonic() - t0
        evals = sampler._parse_joint_evaluation(resp, scc_info.clause_ids, compact=use_compact)
        target_eval = evals.get(target_id)
        score = target_eval.overall_risk_score if target_eval else 0.0
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.warning(f"Joint LLM trial {trial_id} failed: {e}")
        score = 0.0

    return {"trial": trial_id, "score": score, "detected": score >= HIGH_RISK_THRESHOLD, "time": elapsed}


async def run_joint_llm_multi(llm_client, graph, config, scc_info_orig, target_id, num_trials=5):
    """Run multiple Joint LLM trials concurrently."""
    pg = perturb_type_c(graph, scc_info_orig.clause_ids, target_id)
    pg = _prepare_graph(pg, config)

    scc_info = None
    for s in pg.sccs:
        if target_id in s.clause_ids:
            scc_info = s
            break
    if not scc_info:
        return {"trials": [], "avg_score": 0.0, "det_rate": 0.0, "total_time": 0.0}

    sampler = SCCSampler(llm_client, config)
    tasks = [
        run_joint_llm_single(llm_client, pg, scc_info, target_id, sampler, i)
        for i in range(num_trials)
    ]
    trials = await asyncio.gather(*tasks)

    scores = [t["score"] for t in trials]
    det_count = sum(1 for t in trials if t["detected"])
    return {
        "trials": trials,
        "avg_score": sum(scores) / len(scores) if scores else 0.0,
        "det_rate": det_count / len(trials) if trials else 0.0,
        "det_count": det_count,
        "total_trials": len(trials),
        "total_time": max(t["time"] for t in trials),
    }


async def run_mcgs_deep(llm_client, graph, config, target_id, scc_node_ids):
    """MCGS with enhanced parameters: 10 samples, 50 rollouts."""
    pg = perturb_type_c(graph, scc_node_ids, target_id)

    scc_set = set(scc_node_ids)
    sub_clauses = {cid: pg.clauses[cid] for cid in scc_node_ids if cid in pg.clauses}
    sub_edges = [e for e in pg.edges if e.source in scc_set and e.target in scc_set]

    sub_graph = DependencyGraph(
        contract_id="sub_scc",
        clauses=sub_clauses,
        edges=sub_edges,
        topological_order=[{"id": "scc_target", "type": "scc"}],
    )
    scc_info = SCCInfo(
        id="scc_target",
        clause_ids=list(scc_node_ids),
        internal_edges=sub_edges,
        is_collapsed=False,
    )
    sub_graph.sccs = [scc_info]

    enh_config = json.loads(json.dumps(config))
    enh_config["scc"]["num_samples"] = 10
    enh_config["mcgs"] = {
        "num_rollouts": 50,
        "ucb_exploration_weight": 1.414,
        "early_stopping": False,
    }
    enh_config.setdefault("pruning", {}).update({
        "cvar_alpha": 0.8,
        "cvar_safe_threshold": 0.4,
    })
    enh_config["detection"] = {
        "alpha": 0.1,
        "min_rollouts": 5,
        "confidence_delta": 0.05,
    }

    sampler = SCCSampler(llm_client, enh_config)
    online_mcgs = OnlineConformalMCGS(enh_config)

    t0 = time.monotonic()

    scc_samples = await sampler.sample_all_sccs(sub_graph, {})
    search_tree = sampler.build_search_tree(sub_graph, scc_samples)

    dom_pruner = DominancePruner(enh_config)
    dom_pruner.prune(search_tree)

    active = {sid: n for sid, n in search_tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())

    if not active or total_active == 0:
        rollout_results = []
    else:
        rollout_results = online_mcgs.search(search_tree, {}, sub_graph)

    aggregator = Aggregator(enh_config)
    result = aggregator.aggregate(rollout_results, {}, {}, sub_graph)
    identifier = RiskIdentifier(enh_config)
    result = identifier.identify(result, sub_graph)

    elapsed = time.monotonic() - t0

    cr = result.clause_results.get(target_id)
    score = cr.mean_risk_score if cr else 0.0
    std_score = cr.std_risk_score if cr else 0.0
    max_score = cr.max_risk_score if cr else 0.0

    online_detected = target_id in online_mcgs.detected_clauses
    high_risk = target_id in result.high_risk_clauses
    uncertain = target_id in result.uncertain_clauses
    detected = high_risk or uncertain or online_detected

    det_log = [d for d in online_mcgs.detection_log if d["clause_id"] == target_id]

    return {
        "mean_score": score,
        "std_score": std_score,
        "max_score": max_score,
        "detected": detected,
        "hr_detected": high_risk,
        "unc_detected": uncertain,
        "oc_detected": online_detected,
        "oc_log": det_log,
        "rollouts_completed": len(rollout_results),
        "active_branches": total_active,
        "running_threshold": online_mcgs.running_threshold,
        "time": elapsed,
    }


async def run_single_case(llm_client, graph, config, scc_info, target_id, label):
    """Run both Joint LLM (5 trials) and MCGS concurrently for one case."""
    logger.info(f"\n{'='*70}")
    logger.info(f"CASE: {label}")
    logger.info(f"{'='*70}")

    joint_task = run_joint_llm_multi(
        llm_client, graph, config, scc_info, target_id, num_trials=5
    )
    mcgs_task = run_mcgs_deep(
        llm_client, graph, config, target_id, scc_info.clause_ids
    )

    joint_result, mcgs_result = await asyncio.gather(joint_task, mcgs_task)

    logger.info(f"  [Joint LLM x5] avg_score={joint_result['avg_score']:.3f}, "
                f"det_rate={joint_result['det_rate']:.0%} ({joint_result['det_count']}/{joint_result['total_trials']}), "
                f"time={joint_result['total_time']:.1f}s")
    for t in joint_result["trials"]:
        logger.info(f"    trial {t['trial']}: score={t['score']:.3f}, det={'Y' if t['detected'] else 'N'}")

    logger.info(f"  [MCGS Deep] mean={mcgs_result['mean_score']:.3f}, "
                f"std={mcgs_result['std_score']:.3f}, max={mcgs_result['max_score']:.3f}")
    logger.info(f"    detected={mcgs_result['detected']}, "
                f"HR={mcgs_result['hr_detected']}, UNC={mcgs_result['unc_detected']}, OC={mcgs_result['oc_detected']}")
    logger.info(f"    rollouts={mcgs_result['rollouts_completed']}, "
                f"branches={mcgs_result['active_branches']}, "
                f"threshold={mcgs_result['running_threshold']:.4f}, "
                f"time={mcgs_result['time']:.1f}s")
    if mcgs_result["oc_log"]:
        for entry in mcgs_result["oc_log"]:
            logger.info(f"    OC detection: z={entry['z_score']:.2f}, rank={entry['avg_rank']:.2f}, "
                        f"exc={entry['exceedance_frac']:.2f}, tests={entry['tests_passed']}")

    return {
        "target_id": target_id,
        "scc_size": len(scc_info.clause_ids),
        "joint": joint_result,
        "mcgs": mcgs_result,
    }


async def main():
    logger.info("=" * 70)
    logger.info("DEEP EXPERIMENT: 5-node Type C · Enhanced MCGS")
    logger.info("  Joint LLM: 5 parallel trials")
    logger.info("  MCGS: 10 samples, 50 rollouts, no early stopping")
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

    # Find 5-node SCCs
    target_cases = []
    for scc in sorted(graph.sccs, key=lambda s: -len(s.clause_ids)):
        if len(scc.clause_ids) != 5:
            continue
        edge_pairs = set()
        for e in scc.internal_edges:
            edge_pairs.add((e.source, e.target))
        mutual = [(a, b) for a, b in edge_pairs if (b, a) in edge_pairs]
        if not mutual:
            continue
        target_id = mutual[0][0]
        total_chars = sum(len(graph.clauses[cid].content or '') for cid in scc.clause_ids)
        target_cases.append({
            "scc": scc,
            "target_id": target_id,
            "size": len(scc.clause_ids),
            "tokens": total_chars // 3,
        })

    logger.info(f"Found {len(target_cases)} target 5-node SCCs:")
    for tc in target_cases:
        logger.info(f"  {tc['target_id']}: {tc['size']}n, ~{tc['tokens']} tokens")

    t_global = time.monotonic()

    # Run ALL cases in parallel
    tasks = [
        run_single_case(
            llm_client, graph, config,
            tc["scc"], tc["target_id"],
            f"{tc['target_id']} ({tc['size']}n, ~{tc['tokens']}tok)"
        )
        for tc in target_cases
    ]
    results = await asyncio.gather(*tasks)

    total_time = time.monotonic() - t_global
    logger.info(f"\n{'='*70}")
    logger.info(f"ALL DONE in {total_time:.1f}s")
    logger.info(f"{'='*70}")

    # Summary
    output = {
        "experiment": "deep_5n_typec",
        "description": "Enhanced MCGS (50 rollouts, 10 samples) vs Joint LLM (5 trials) on 5-node Type C",
        "config": {
            "mcgs_num_samples": 10,
            "mcgs_num_rollouts": 50,
            "mcgs_early_stopping": False,
            "joint_num_trials": 5,
            "perturbation": "type_c",
        },
        "cases": [],
    }

    for r in results:
        case_data = {
            "target_id": r["target_id"],
            "scc_size": r["scc_size"],
            "joint_avg_score": r["joint"]["avg_score"],
            "joint_det_rate": r["joint"]["det_rate"],
            "joint_det_count": r["joint"]["det_count"],
            "joint_total_trials": r["joint"]["total_trials"],
            "joint_trial_scores": [t["score"] for t in r["joint"]["trials"]],
            "joint_time": r["joint"]["total_time"],
            "mcgs_mean_score": r["mcgs"]["mean_score"],
            "mcgs_std_score": r["mcgs"]["std_score"],
            "mcgs_max_score": r["mcgs"]["max_score"],
            "mcgs_detected": r["mcgs"]["detected"],
            "mcgs_hr_detected": r["mcgs"]["hr_detected"],
            "mcgs_unc_detected": r["mcgs"]["unc_detected"],
            "mcgs_oc_detected": r["mcgs"]["oc_detected"],
            "mcgs_rollouts": r["mcgs"]["rollouts_completed"],
            "mcgs_branches": r["mcgs"]["active_branches"],
            "mcgs_threshold": r["mcgs"]["running_threshold"],
            "mcgs_oc_log": r["mcgs"]["oc_log"],
            "mcgs_time": r["mcgs"]["time"],
        }
        output["cases"].append(case_data)

        logger.info(f"\n--- {r['target_id']} ---")
        logger.info(f"  Joint LLM:  avg={case_data['joint_avg_score']:.3f}, "
                    f"det_rate={case_data['joint_det_rate']:.0%}, "
                    f"scores={case_data['joint_trial_scores']}")
        logger.info(f"  MCGS:       mean={case_data['mcgs_mean_score']:.3f}, "
                    f"std={case_data['mcgs_std_score']:.3f}, "
                    f"max={case_data['mcgs_max_score']:.3f}")
        logger.info(f"  MCGS Det:   composite={case_data['mcgs_detected']}, "
                    f"HR={case_data['mcgs_hr_detected']}, "
                    f"UNC={case_data['mcgs_unc_detected']}, "
                    f"OC={case_data['mcgs_oc_detected']}")

    output_path = Path("experiments/results/deep_5n_typec.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info(f"\nResults saved to {output_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
