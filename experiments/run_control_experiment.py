"""Control experiment: Run Joint LLM and MCGS on UNPERTURBED SCC.

Tests false positive rate: does the method report "defect_found" when
there is NO injected defect?

This is critical for scientific rigor — if Joint LLM always says
"defect_found" on any SCC (because circular deps look suspicious),
then its 100% detection rate is meaningless.
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
from src.modules.scc_sampler import SCCSampler
from src.modules.aggregator import Aggregator
from src.modules.risk_identifier import RiskIdentifier
from src.modules.pruning import DominancePruner
from src.modules.online_conformal_mcgs import OnlineConformalMCGS


def _build_verdict_prompt(clauses, internal_edges):
    """Same fair prompt as verdict experiment — NO defect-type hints."""
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


async def run_joint_single(llm_client, graph, scc_info, trial_id):
    """Single Joint LLM trial on UNPERTURBED SCC."""
    clauses = [graph.clauses[cid] for cid in scc_info.clause_ids]
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

        return {
            "trial": trial_id,
            "found_defect": found,
            "verdict": verdict,
            "reasoning": resp.get("reasoning", ""),
            "issues_found": issues_found,
            "num_flagged": len(issues_found),
            "time": elapsed,
            "json_failed": False,
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        return {
            "trial": trial_id,
            "found_defect": False,
            "verdict": "json_error",
            "reasoning": str(e),
            "issues_found": [],
            "num_flagged": 0,
            "time": elapsed,
            "json_failed": True,
        }


async def run_mcgs_on_clean(llm_client, graph, config, scc_info):
    """MCGS on UNPERTURBED SCC."""
    scc_set = set(scc_info.clause_ids)
    sub_clauses = {cid: graph.clauses[cid] for cid in scc_info.clause_ids}
    sub_edges = [e for e in graph.edges if e.source in scc_set and e.target in scc_set]

    sub_graph = DependencyGraph(
        contract_id="sub_scc",
        clauses=sub_clauses,
        edges=sub_edges,
        topological_order=[{"id": "scc_target", "type": "scc"}],
    )
    sub_scc = SCCInfo(
        id="scc_target",
        clause_ids=list(scc_info.clause_ids),
        internal_edges=sub_edges,
        is_collapsed=False,
    )
    sub_graph.sccs = [sub_scc]

    n_clauses = len(scc_info.clause_ids)
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
    DominancePruner(enh_config).prune(search_tree)

    active = {sid: n for sid, n in search_tree.nodes.items() if n.active_branches}
    total_active = sum(len(n.active_branches) for n in active.values())

    rollout_results = online_mcgs.search(search_tree, {}, sub_graph) if active and total_active else []

    aggregator = Aggregator(enh_config)
    result = aggregator.aggregate(rollout_results, {}, {}, sub_graph)
    identifier = RiskIdentifier(enh_config)
    result = identifier.identify(result, sub_graph)
    elapsed = time.monotonic() - t0

    all_hr = list(result.high_risk_clauses)
    all_unc = list(result.uncertain_clauses)
    all_oc = list(online_mcgs.detected_clauses)
    found_defect = len(all_hr) > 0 or len(all_unc) > 0 or len(all_oc) > 0

    clause_details = {}
    for cid in scc_info.clause_ids:
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

    return {
        "found_defect": found_defect,
        "high_risk_clauses": all_hr,
        "uncertain_clauses": all_unc,
        "oc_detected_clauses": all_oc,
        "total_flagged": len(set(all_hr) | set(all_unc) | set(all_oc)),
        "total_clauses": len(scc_info.clause_ids),
        "clause_details": clause_details,
        "rollouts_completed": len(rollout_results),
        "time": elapsed,
    }


async def main():
    import sys
    target_sizes = {int(a) for a in sys.argv[1:]} or {24}

    logger.info("=" * 70)
    logger.info("CONTROL EXPERIMENT: No Perturbation (False Positive Test)")
    logger.info("  Joint LLM x5 + MCGS on CLEAN (unperturbed) SCC")
    logger.info(f"  Target sizes: {sorted(target_sizes)}")
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
        target_cases.append({"scc": scc, "size": len(scc.clause_ids)})

    if not target_cases:
        logger.error("No target SCCs found!")
        return

    tc = target_cases[0]
    scc_info = tc["scc"]
    logger.info(f"Target SCC: {tc['size']}n, clauses={list(scc_info.clause_ids)}")

    t0 = time.monotonic()

    joint_tasks = [run_joint_single(llm_client, graph, scc_info, i) for i in range(5)]
    mcgs_task = run_mcgs_on_clean(llm_client, graph, config, scc_info)
    all_results = await asyncio.gather(*joint_tasks, mcgs_task)

    joint_trials = list(all_results[:5])
    mcgs_result = all_results[5]
    total_time = time.monotonic() - t0

    logger.info(f"\n{'='*70}")
    logger.info(f"CONTROL RESULTS (NO PERTURBATION) — {total_time:.1f}s")
    logger.info(f"{'='*70}")

    joint_det = sum(1 for t in joint_trials if t["found_defect"])
    joint_fp_rate = joint_det / len(joint_trials)
    logger.info(f"\n  [Joint LLM x5] FALSE POSITIVE RATE: {joint_fp_rate:.0%} ({joint_det}/5)")
    for t in joint_trials:
        status = "FP!" if t["found_defect"] else "OK"
        logger.info(f"    trial {t['trial']}: {status} | flagged {t['num_flagged']}/{tc['size']} clauses")
        logger.info(f"      reasoning: {t['reasoning'][:200]}")

    mcgs_fp = mcgs_result["found_defect"]
    logger.info(f"\n  [MCGS] FALSE POSITIVE: {'YES' if mcgs_fp else 'NO'}")
    logger.info(f"    flagged={mcgs_result['total_flagged']}/{mcgs_result['total_clauses']}")
    logger.info(f"    HR={mcgs_result['high_risk_clauses']}")
    logger.info(f"    OC={mcgs_result['oc_detected_clauses']}")

    output = {
        "experiment": "control_no_perturbation",
        "description": "False positive test: same prompt on CLEAN SCC (no injected defect)",
        "scc_size": tc["size"],
        "scc_clause_ids": list(scc_info.clause_ids),
        "joint": {
            "false_positive_rate": joint_fp_rate,
            "det_count": joint_det,
            "total_trials": len(joint_trials),
            "trials": [{
                "trial": t["trial"],
                "found_defect": t["found_defect"],
                "verdict": t["verdict"],
                "reasoning": t["reasoning"][:300],
                "issues_found": t["issues_found"],
                "num_flagged": t["num_flagged"],
                "json_failed": t["json_failed"],
                "time": t["time"],
            } for t in joint_trials],
        },
        "mcgs": {
            "false_positive": mcgs_fp,
            "total_flagged": mcgs_result["total_flagged"],
            "total_clauses": mcgs_result["total_clauses"],
            "high_risk_clauses": mcgs_result["high_risk_clauses"],
            "oc_detected_clauses": mcgs_result["oc_detected_clauses"],
            "clause_details": mcgs_result["clause_details"],
            "rollouts": mcgs_result["rollouts_completed"],
            "time": mcgs_result["time"],
        },
        "total_time": total_time,
    }

    sizes_str = "_".join(str(s) for s in sorted(target_sizes))
    output_path = Path(f"experiments/results/control_{sizes_str}n.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info(f"\nResults saved to {output_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
