"""Verdict-based experiment: Binary detection (Found / Not Found).

Key changes from score-based approach:
  1. Joint LLM: asks "found_defect: true/false" directly (no score threshold)
  2. MCGS: detects if ANY clause in SCC is flagged (not just target_id)

Runs on: 5n cases (bgb_240a, bgb_555c) + 9n case (bgb_275), Type C only.
All cases run in parallel. Joint LLM x5 trials per case.
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


def _prepare_graph(graph: DependencyGraph, config: dict) -> DependencyGraph:
    DomainGraphPruner(config).prune(graph)
    return TarjanSCCDetector().detect(graph)


def _build_verdict_prompt(clauses, internal_edges):
    """Build a binary-verdict prompt: no scores, just 'found_defect: true/false'."""
    clauses_fmt = "\n\n".join(
        f"### {c.id}: {c.title}\n{c.content}" for c in clauses
    )
    deps_fmt = "\n".join(
        f"- {e.source} → {e.target} ({e.dependency_type.value}): {e.reasoning}"
        for e in internal_edges
    ) or "None"

    clause_ids = [c.id for c in clauses]

    return (
        "You are a legal analyst. Below is a set of interdependent legal clauses "
        "that form a cycle of mutual references.\n\n"
        f"## Clauses\n{clauses_fmt}\n\n"
        f"## Dependency Graph\n{deps_fmt}\n\n"
        "## Task\n"
        "Analyze whether there is any logical inconsistency, conflict, or drafting "
        "error among these clauses. Consider how they interact with each other.\n\n"
        "For each clause, determine whether it contains or is affected by any issue.\n\n"
        "Output STRICTLY as JSON:\n"
        '{"verdict": "defect_found" or "no_defect",\n'
        ' "reasoning": "brief overall explanation",\n'
        ' "clause_verdicts": {\n'
        + ",\n".join(
            f'   "{cid}": {{"has_issue": true/false, "explanation": "..."}}'
            for cid in clause_ids
        )
        + "\n }}"
    )


async def run_joint_verdict_single(llm_client, perturbed_graph, scc_info, trial_id):
    """Single Joint LLM trial with binary verdict."""
    clauses = [perturbed_graph.clauses[cid] for cid in scc_info.clause_ids]
    prompt = _build_verdict_prompt(clauses, scc_info.internal_edges)

    max_tok = min(8192, max(4096, len(clauses) * 300))

    t0 = time.monotonic()
    try:
        resp = await llm_client.call_json(prompt, temperature=0.0, max_tokens=max_tok)
        elapsed = time.monotonic() - t0

        verdict = resp.get("verdict", "unknown")
        found = verdict == "defect_found"

        clause_verdicts = resp.get("clause_verdicts", {})
        issues_found = [
            cid for cid, v in clause_verdicts.items()
            if isinstance(v, dict) and v.get("has_issue", False)
        ]
        explanations = {
            cid: clause_verdicts[cid].get("explanation", "")
            for cid in issues_found
            if isinstance(clause_verdicts.get(cid), dict)
        }

        return {
            "trial": trial_id,
            "found_defect": found,
            "verdict": verdict,
            "reasoning": resp.get("reasoning", ""),
            "issues_found": issues_found,
            "explanations": explanations,
            "time": elapsed,
            "json_failed": False,
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.warning(f"Joint LLM trial {trial_id} failed: {e}")
        return {
            "trial": trial_id,
            "found_defect": False,
            "verdict": "json_error",
            "reasoning": str(e),
            "issues_found": [],
            "explanations": {},
            "time": elapsed,
            "json_failed": True,
        }


async def run_joint_verdict_multi(llm_client, graph, config, scc_info_orig, target_id, num_trials=5):
    """Run multiple Joint LLM verdict trials concurrently."""
    pg = perturb_type_c(graph, scc_info_orig.clause_ids, target_id)
    pg = _prepare_graph(pg, config)

    scc_info = None
    for s in pg.sccs:
        if target_id in s.clause_ids:
            scc_info = s
            break
    if not scc_info:
        return {"trials": [], "det_rate": 0.0, "json_fail_rate": 0.0}

    tasks = [
        run_joint_verdict_single(llm_client, pg, scc_info, i)
        for i in range(num_trials)
    ]
    trials = await asyncio.gather(*tasks)

    det_count = sum(1 for t in trials if t["found_defect"])
    json_fails = sum(1 for t in trials if t["json_failed"])

    return {
        "trials": trials,
        "det_rate": det_count / len(trials) if trials else 0.0,
        "det_count": det_count,
        "json_fail_count": json_fails,
        "json_fail_rate": json_fails / len(trials) if trials else 0.0,
        "total_trials": len(trials),
        "total_time": max(t["time"] for t in trials) if trials else 0.0,
    }


async def run_mcgs_structural(llm_client, graph, config, target_id, scc_node_ids):
    """MCGS with structural detection: ANY clause flagged = detected."""
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

    n_clauses = len(scc_node_ids)
    num_samples = min(15, max(10, n_clauses // 2))
    num_rollouts = min(100, max(50, n_clauses * 3))

    enh_config = json.loads(json.dumps(config))
    enh_config["scc"]["num_samples"] = num_samples
    enh_config["mcgs"] = {
        "num_rollouts": num_rollouts,
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

    # Structural detection: ANY clause flagged = SCC has problem
    all_hr = list(result.high_risk_clauses)
    all_unc = list(result.uncertain_clauses)
    all_oc = list(online_mcgs.detected_clauses)

    found_defect = len(all_hr) > 0 or len(all_unc) > 0 or len(all_oc) > 0

    # Per-clause detail
    clause_details = {}
    for cid in scc_node_ids:
        cr = result.clause_results.get(cid)
        if cr:
            clause_details[cid] = {
                "mean_score": cr.mean_risk_score,
                "max_score": cr.max_risk_score,
                "std_score": cr.std_risk_score,
                "is_high_risk": cid in all_hr,
                "is_uncertain": cid in all_unc,
                "is_oc_detected": cid in all_oc,
            }

    oc_log = online_mcgs.detection_log

    return {
        "found_defect": found_defect,
        "high_risk_clauses": all_hr,
        "uncertain_clauses": all_unc,
        "oc_detected_clauses": all_oc,
        "total_flagged": len(set(all_hr) | set(all_unc) | set(all_oc)),
        "total_clauses": len(scc_node_ids),
        "clause_details": clause_details,
        "oc_log": oc_log,
        "rollouts_completed": len(rollout_results),
        "active_branches": total_active,
        "running_threshold": online_mcgs.running_threshold,
        "time": elapsed,
    }


async def run_single_case(llm_client, graph, config, scc_info, target_id, label):
    """Run both Joint LLM verdict and MCGS structural concurrently."""
    logger.info(f"\n{'='*70}")
    logger.info(f"CASE: {label}")
    logger.info(f"{'='*70}")

    joint_task = run_joint_verdict_multi(
        llm_client, graph, config, scc_info, target_id, num_trials=5
    )
    mcgs_task = run_mcgs_structural(
        llm_client, graph, config, target_id, scc_info.clause_ids
    )

    joint_result, mcgs_result = await asyncio.gather(joint_task, mcgs_task)

    # Joint LLM summary
    logger.info(f"  [Joint LLM x5] det_rate={joint_result['det_rate']:.0%} "
                f"({joint_result['det_count']}/{joint_result['total_trials']}), "
                f"json_fails={joint_result['json_fail_count']}, "
                f"time={joint_result['total_time']:.1f}s")
    for t in joint_result["trials"]:
        status = "FOUND" if t["found_defect"] else ("JSON_ERR" if t["json_failed"] else "NOT_FOUND")
        issues = ", ".join(t["issues_found"]) if t["issues_found"] else "—"
        logger.info(f"    trial {t['trial']}: {status} | flagged=[{issues}]")

    # MCGS summary
    logger.info(f"  [MCGS Structural] found_defect={mcgs_result['found_defect']}, "
                f"flagged={mcgs_result['total_flagged']}/{mcgs_result['total_clauses']}, "
                f"HR={mcgs_result['high_risk_clauses']}, "
                f"UNC={mcgs_result['uncertain_clauses']}, "
                f"OC={mcgs_result['oc_detected_clauses']}, "
                f"time={mcgs_result['time']:.1f}s")
    for cid, d in mcgs_result["clause_details"].items():
        flags = []
        if d["is_high_risk"]: flags.append("HR")
        if d["is_uncertain"]: flags.append("UNC")
        if d["is_oc_detected"]: flags.append("OC")
        flag_str = ",".join(flags) if flags else "—"
        logger.info(f"    {cid}: mean={d['mean_score']:.3f}, max={d['max_score']:.3f}, "
                    f"std={d['std_score']:.3f}, flags=[{flag_str}]")

    return {
        "target_id": target_id,
        "scc_size": len(scc_info.clause_ids),
        "scc_clause_ids": list(scc_info.clause_ids),
        "joint": joint_result,
        "mcgs": mcgs_result,
    }


async def main():
    import sys
    target_sizes = set()
    for arg in sys.argv[1:]:
        target_sizes.add(int(arg))
    if not target_sizes:
        target_sizes = {5}

    logger.info("=" * 70)
    logger.info("VERDICT EXPERIMENT (FAIR): Binary Detection (Found / Not Found)")
    logger.info("  Joint LLM: generic prompt (NO defect-type hints)")
    logger.info("  MCGS: structural detection (ANY clause flagged = detected)")
    logger.info(f"  Type C perturbation · target sizes: {sorted(target_sizes)}")
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

    # Find target SCCs by requested sizes
    target_cases = []
    for scc in sorted(graph.sccs, key=lambda s: -len(s.clause_ids)):
        if len(scc.clause_ids) not in target_sizes:
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

    logger.info(f"Found {len(target_cases)} target SCCs:")
    for tc in target_cases:
        logger.info(f"  {tc['target_id']}: {tc['size']}n, ~{tc['tokens']} tokens, "
                    f"clauses={list(tc['scc'].clause_ids)}")

    t_global = time.monotonic()

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

    output = {
        "experiment": "verdict_typec_fair",
        "description": "Fair binary verdict: Joint LLM (generic prompt, no defect-type hints) vs MCGS (structural detection) on Type C",
        "config": {
            "mcgs_num_samples": 10,
            "mcgs_num_rollouts": 50,
            "joint_num_trials": 5,
            "perturbation": "type_c",
            "detection_mode": "structural",
        },
        "cases": [],
    }

    for r in results:
        # Simplify trials for JSON
        joint_trials_simple = [{
            "trial": t["trial"],
            "found_defect": t["found_defect"],
            "verdict": t["verdict"],
            "reasoning": t["reasoning"][:300],
            "issues_found": t["issues_found"],
            "json_failed": t["json_failed"],
            "time": t["time"],
        } for t in r["joint"]["trials"]]

        case_data = {
            "target_id": r["target_id"],
            "scc_size": r["scc_size"],
            "scc_clause_ids": r["scc_clause_ids"],
            # Joint LLM
            "joint_found_defect_rate": r["joint"]["det_rate"],
            "joint_found_count": r["joint"]["det_count"],
            "joint_json_fail_count": r["joint"]["json_fail_count"],
            "joint_total_trials": r["joint"]["total_trials"],
            "joint_trials": joint_trials_simple,
            "joint_time": r["joint"]["total_time"],
            # MCGS
            "mcgs_found_defect": r["mcgs"]["found_defect"],
            "mcgs_high_risk_clauses": r["mcgs"]["high_risk_clauses"],
            "mcgs_uncertain_clauses": r["mcgs"]["uncertain_clauses"],
            "mcgs_oc_detected_clauses": r["mcgs"]["oc_detected_clauses"],
            "mcgs_total_flagged": r["mcgs"]["total_flagged"],
            "mcgs_clause_details": r["mcgs"]["clause_details"],
            "mcgs_rollouts": r["mcgs"]["rollouts_completed"],
            "mcgs_time": r["mcgs"]["time"],
        }
        output["cases"].append(case_data)

        verdict_j = f"{r['joint']['det_rate']:.0%} ({r['joint']['det_count']}/{r['joint']['total_trials']})"
        verdict_m = "FOUND" if r["mcgs"]["found_defect"] else "NOT FOUND"
        logger.info(f"\n--- {r['target_id']} ({r['scc_size']}n) ---")
        logger.info(f"  Joint LLM:  {verdict_j} found defect, {r['joint']['json_fail_count']} json errors")
        logger.info(f"  MCGS:       {verdict_m} — {r['mcgs']['total_flagged']}/{r['scc_size']} clauses flagged")

    sizes_str = "_".join(str(s) for s in sorted(target_sizes))
    output_path = Path(f"experiments/results/verdict_fair_{sizes_str}n.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info(f"\nResults saved to {output_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
