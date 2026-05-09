"""Comprehensive Ablation Suite: Delta Detection vs Pure LLM.

Three experiment groups, all with Joint LLM baseline comparison:

  Exp 1 — Cross-Scale:  5n, 9n, 24n   (does delta work at every scale?)
  Exp 2 — Multi-Target: 24n × 3 targets (is delta robust to injection site?)
  Exp 3 — Repeated:     24n × 3 trials  (is delta statistically stable?)

Each condition runs:
  • Clean MCGS  (baseline, no perturbation)
  • Perturbed MCGS  (Type C scope expansion)
  • Joint LLM × 5 trials on Clean  (FP baseline)
  • Joint LLM × 5 trials on Perturbed
  • Delta = Perturbed − Clean  →  rank target node

Reuses existing results where available to save LLM calls.
"""
from __future__ import annotations

import asyncio
import copy
import json
import sys
import time
from pathlib import Path
from typing import Any

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


def _build_verdict_prompt(clauses, internal_edges):
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


# ── Joint LLM ──────────────────────────────────────────────────────


async def _joint_llm_single(llm_client, graph, scc_info, trial_id):
    clauses = [graph.clauses[cid] for cid in scc_info.clause_ids]
    prompt = _build_verdict_prompt(clauses, scc_info.internal_edges)
    max_tok = min(8192, max(4096, len(clauses) * 300))
    t0 = time.monotonic()
    try:
        resp = await llm_client.call_json(prompt, temperature=0.0, max_tokens=max_tok)
        elapsed = time.monotonic() - t0
        verdict = resp.get("verdict", "unknown")
        found = verdict == "defect_found"
        cv = resp.get("clause_verdicts", {})
        issues = [cid for cid, v in cv.items()
                  if isinstance(v, dict) and v.get("has_issue")]
        return {
            "trial": trial_id, "found_defect": found, "verdict": verdict,
            "reasoning": resp.get("reasoning", "")[:300],
            "issues_found": issues, "num_flagged": len(issues),
            "time": elapsed, "json_failed": False,
        }
    except Exception as e:
        return {
            "trial": trial_id, "found_defect": False, "verdict": "json_error",
            "reasoning": str(e)[:300], "issues_found": [], "num_flagged": 0,
            "time": time.monotonic() - t0, "json_failed": True,
        }


async def run_joint_llm(llm_client, graph, scc_info, num_trials=5, label=""):
    tasks = [_joint_llm_single(llm_client, graph, scc_info, i) for i in range(num_trials)]
    trials = await asyncio.gather(*tasks)
    det = sum(1 for t in trials if t["found_defect"])
    jf = sum(1 for t in trials if t["json_failed"])
    logger.info(f"  [Joint LLM {label}] det={det}/{len(trials)}, json_fail={jf}")
    return {
        "trials": trials,
        "det_rate": det / len(trials) if trials else 0,
        "det_count": det, "json_fail_count": jf,
        "total_trials": len(trials),
    }


# ── MCGS ────────────────────────────────────────────────────────────


async def run_mcgs(llm_client, graph, config, scc_info, label=""):
    scc_set = set(scc_info.clause_ids)
    sub_clauses = {cid: graph.clauses[cid] for cid in scc_info.clause_ids if cid in graph.clauses}
    sub_edges = [e for e in graph.edges if e.source in scc_set and e.target in scc_set]
    sub_graph = DependencyGraph(
        contract_id="sub_scc", clauses=sub_clauses, edges=sub_edges,
        topological_order=[{"id": "scc_target", "type": "scc"}],
    )
    sub_scc = SCCInfo(
        id="scc_target", clause_ids=list(scc_info.clause_ids),
        internal_edges=sub_edges, is_collapsed=False,
    )
    sub_graph.sccs = [sub_scc]

    n = len(scc_info.clause_ids)
    num_samples = min(15, max(10, n // 2))
    num_rollouts = min(100, max(50, n * 3))

    ec = json.loads(json.dumps(config))
    ec["scc"]["num_samples"] = num_samples
    ec["mcgs"] = {"num_rollouts": num_rollouts, "ucb_exploration_weight": 1.414, "early_stopping": False}
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

    hr = list(result.high_risk_clauses)
    unc = list(result.uncertain_clauses)
    oc = list(oc_mcgs.detected_clauses)

    details = {}
    for cid in scc_info.clause_ids:
        cr = result.clause_results.get(cid)
        if cr:
            details[cid] = {
                "mean_score": cr.mean_risk_score, "max_score": cr.max_risk_score,
                "std_score": cr.std_risk_score,
                "is_high_risk": cid in hr, "is_uncertain": cid in unc,
                "is_oc_detected": cid in oc,
            }

    logger.info(f"  [MCGS {label}] HR={len(hr)}, UNC={len(unc)}, OC={len(oc)}, time={elapsed:.1f}s")
    return {
        "high_risk_clauses": hr, "uncertain_clauses": unc,
        "oc_detected_clauses": oc,
        "total_flagged": len(set(hr) | set(unc) | set(oc)),
        "total_clauses": n, "clause_details": details,
        "rollouts_completed": len(rollout_results), "time": elapsed,
    }


# ── Delta Computation ───────────────────────────────────────────────


def compute_delta(clean_mcgs: dict, pert_mcgs: dict, target_id: str, all_ids: list[str]):
    cd = clean_mcgs["clause_details"]
    pd = pert_mcgs["clause_details"]
    c_oc = set(clean_mcgs["oc_detected_clauses"])
    p_oc = set(pert_mcgs["oc_detected_clauses"])
    c_hr = set(clean_mcgs["high_risk_clauses"])
    p_hr = set(pert_mcgs["high_risk_clauses"])

    deltas = []
    for cid in all_ids:
        c = cd.get(cid, {})
        p = pd.get(cid, {})
        cm, pm = c.get("mean_score", 0), p.get("mean_score", 0)
        cmx, pmx = c.get("max_score", 0), p.get("max_score", 0)
        cs, ps = c.get("std_score", 0), p.get("std_score", 0)
        oc_ch = "NEW_OC" if cid in p_oc and cid not in c_oc else \
                "LOST_OC" if cid in c_oc and cid not in p_oc else \
                "BOTH_OC" if cid in c_oc and cid in p_oc else ""
        hr_ch = "NEW_HR" if cid in p_hr and cid not in c_hr else \
                "LOST_HR" if cid in c_hr and cid not in p_hr else ""
        deltas.append({
            "cid": cid, "is_target": cid == target_id,
            "clean_mean": cm, "pert_mean": pm, "delta_mean": pm - cm,
            "clean_max": cmx, "pert_max": pmx, "delta_max": pmx - cmx,
            "delta_std": ps - cs, "oc_change": oc_ch, "hr_change": hr_ch,
        })
    deltas.sort(key=lambda x: x["delta_mean"], reverse=True)

    target_rank = next((i + 1 for i, d in enumerate(deltas) if d["is_target"]), len(deltas))
    target_d = next((d for d in deltas if d["is_target"]), None)

    new_oc = sorted(p_oc - c_oc)
    lost_oc = sorted(c_oc - p_oc)
    new_hr = sorted(p_hr - c_hr)

    return {
        "target_id": target_id, "scc_size": len(all_ids),
        "target_rank": target_rank,
        "target_delta_mean": target_d["delta_mean"] if target_d else 0,
        "target_delta_max": target_d["delta_max"] if target_d else 0,
        "new_oc": new_oc, "lost_oc": lost_oc, "new_hr": new_hr,
        "deltas": deltas,
    }


# ── Full Run for one (scc, target) pair ─────────────────────────────


async def run_condition(llm_client, graph, config, scc_info, target_id, label):
    """Run Clean+Perturbed for both Joint LLM and MCGS, then compute delta."""
    logger.info(f"\n{'='*70}\n  {label}\n{'='*70}")

    pg = perturb_type_c(graph, scc_info.clause_ids, target_id)
    DomainGraphPruner(config).prune(pg)
    pg = TarjanSCCDetector().detect(pg)
    pert_scc = None
    for s in pg.sccs:
        if target_id in s.clause_ids:
            pert_scc = s
            break
    if not pert_scc:
        logger.error(f"Cannot find perturbed SCC for {target_id}")
        return None

    t0 = time.monotonic()
    (clean_joint, pert_joint, clean_mcgs, pert_mcgs) = await asyncio.gather(
        run_joint_llm(llm_client, graph, scc_info, 5, f"Clean {label}"),
        run_joint_llm(llm_client, pg, pert_scc, 5, f"Pert {label}"),
        run_mcgs(llm_client, graph, config, scc_info, f"Clean {label}"),
        run_mcgs(llm_client, pg, config, pert_scc, f"Pert {label}"),
    )
    elapsed = time.monotonic() - t0

    all_ids = sorted(scc_info.clause_ids)
    delta = compute_delta(clean_mcgs, pert_mcgs, target_id, all_ids)

    # Joint LLM: target identification rate
    joint_target_in_clean = sum(1 for t in clean_joint["trials"] if target_id in t["issues_found"])
    joint_target_in_pert = sum(1 for t in pert_joint["trials"] if target_id in t["issues_found"])
    joint_avg_flagged_clean = sum(t["num_flagged"] for t in clean_joint["trials"]) / 5
    joint_avg_flagged_pert = sum(t["num_flagged"] for t in pert_joint["trials"]) / 5

    logger.info(f"  [Delta] target={target_id} rank=#{delta['target_rank']}/{len(all_ids)}, "
                f"Δμ={delta['target_delta_mean']:+.3f}")
    logger.info(f"  [Joint] Clean FP={clean_joint['det_rate']:.0%}, "
                f"Pert det={pert_joint['det_rate']:.0%}, "
                f"target in pert={joint_target_in_pert}/5")
    logger.info(f"  Total time: {elapsed:.1f}s")

    return {
        "label": label, "target_id": target_id,
        "scc_size": len(all_ids), "scc_clause_ids": all_ids,
        "clean_joint": clean_joint, "pert_joint": pert_joint,
        "clean_mcgs": clean_mcgs, "pert_mcgs": pert_mcgs,
        "delta": delta,
        "joint_target_in_clean": joint_target_in_clean,
        "joint_target_in_pert": joint_target_in_pert,
        "joint_avg_flagged_clean": joint_avg_flagged_clean,
        "joint_avg_flagged_pert": joint_avg_flagged_pert,
        "total_time": elapsed,
    }


# ── Main ────────────────────────────────────────────────────────────


def find_scc_targets(graph, size):
    """Find SCC of given size and return (scc_info, list_of_valid_targets)."""
    for scc in sorted(graph.sccs, key=lambda s: -len(s.clause_ids)):
        if len(scc.clause_ids) != size:
            continue
        edge_pairs = {(e.source, e.target) for e in scc.internal_edges}
        mutual = [(a, b) for a, b in edge_pairs if (b, a) in edge_pairs]
        if not mutual:
            continue
        targets = list(dict.fromkeys([a for a, _ in mutual]))
        return scc, targets
    return None, []


async def main():
    logger.info("=" * 70)
    logger.info("ABLATION SUITE: Delta Detection vs Pure LLM")
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

    # ── Discover SCCs ───────────────────────────────────────────────
    scc_5, targets_5 = find_scc_targets(graph, 5)
    scc_9, targets_9 = find_scc_targets(graph, 9)
    scc_24, targets_24 = find_scc_targets(graph, 24)

    logger.info(f"5n SCC: {scc_5 is not None}, targets={targets_5[:3] if targets_5 else []}")
    logger.info(f"9n SCC: {scc_9 is not None}, targets={targets_9[:3] if targets_9 else []}")
    logger.info(f"24n SCC: {scc_24 is not None}, targets={targets_24[:5] if targets_24 else []}")

    all_results = {}
    t_global = time.monotonic()

    # ── Exp 1: Cross-Scale (5n, 9n, 24n) ───────────────────────────
    logger.info(f"\n{'#'*70}\n  EXP 1: Cross-Scale Validation\n{'#'*70}")

    exp1_tasks = []
    if scc_5 and targets_5:
        exp1_tasks.append(run_condition(
            llm_client, graph, config, scc_5, targets_5[0], f"5n_{targets_5[0]}"))
    if scc_9 and targets_9:
        exp1_tasks.append(run_condition(
            llm_client, graph, config, scc_9, targets_9[0], f"9n_{targets_9[0]}"))
    if scc_24 and targets_24:
        exp1_tasks.append(run_condition(
            llm_client, graph, config, scc_24, targets_24[0], f"24n_{targets_24[0]}"))

    exp1_results = await asyncio.gather(*exp1_tasks)
    exp1_results = [r for r in exp1_results if r]
    all_results["exp1_cross_scale"] = exp1_results

    # ── Exp 2: Multi-Target on 24n ──────────────────────────────────
    logger.info(f"\n{'#'*70}\n  EXP 2: Multi-Target (24n × 3 targets)\n{'#'*70}")

    exp2_tasks = []
    if scc_24 and len(targets_24) >= 3:
        for t in targets_24[:3]:
            exp2_tasks.append(run_condition(
                llm_client, graph, config, scc_24, t, f"24n_multi_{t}"))
    elif scc_24 and targets_24:
        for t in targets_24:
            exp2_tasks.append(run_condition(
                llm_client, graph, config, scc_24, t, f"24n_multi_{t}"))

    exp2_results = await asyncio.gather(*exp2_tasks)
    exp2_results = [r for r in exp2_results if r]
    all_results["exp2_multi_target"] = exp2_results

    # ── Exp 3: Repeated Trials on 24n ───────────────────────────────
    logger.info(f"\n{'#'*70}\n  EXP 3: Repeated Trials (24n × 3 runs)\n{'#'*70}")

    exp3_tasks = []
    if scc_24 and targets_24:
        primary_target = targets_24[0]
        for i in range(3):
            exp3_tasks.append(run_condition(
                llm_client, graph, config, scc_24, primary_target,
                f"24n_repeat_{i+1}_{primary_target}"))

    exp3_results = await asyncio.gather(*exp3_tasks)
    exp3_results = [r for r in exp3_results if r]
    all_results["exp3_repeated"] = exp3_results

    total_time = time.monotonic() - t_global

    # ── Summary ─────────────────────────────────────────────────────
    logger.info(f"\n{'='*70}")
    logger.info(f"ABLATION SUITE COMPLETE — {total_time:.0f}s")
    logger.info(f"{'='*70}")

    summary_rows = []

    def summarize(exp_name, results_list):
        for r in results_list:
            d = r["delta"]
            row = {
                "experiment": exp_name,
                "label": r["label"],
                "scc_size": r["scc_size"],
                "target_id": r["target_id"],
                "mcgs_delta_rank": d["target_rank"],
                "mcgs_delta_mean": d["target_delta_mean"],
                "mcgs_new_oc": d["new_oc"],
                "joint_clean_fp_rate": r["clean_joint"]["det_rate"],
                "joint_pert_det_rate": r["pert_joint"]["det_rate"],
                "joint_target_in_pert": r["joint_target_in_pert"],
                "joint_avg_flagged_clean": r["joint_avg_flagged_clean"],
                "joint_avg_flagged_pert": r["joint_avg_flagged_pert"],
            }
            summary_rows.append(row)
            logger.info(
                f"  {row['label']:30s} | size={row['scc_size']:>2} | "
                f"MCGS Δrank=#{row['mcgs_delta_rank']:>2}/{row['scc_size']} | "
                f"Δμ={row['mcgs_delta_mean']:+.3f} | "
                f"Joint FP={row['joint_clean_fp_rate']:.0%} det={row['joint_pert_det_rate']:.0%} "
                f"target={row['joint_target_in_pert']}/5"
            )

    summarize("cross_scale", all_results.get("exp1_cross_scale", []))
    summarize("multi_target", all_results.get("exp2_multi_target", []))
    summarize("repeated", all_results.get("exp3_repeated", []))

    # ── Save ────────────────────────────────────────────────────────
    output = {
        "experiment": "ablation_suite",
        "total_time": total_time,
        "summary": summary_rows,
        "exp1_cross_scale": [{k: v for k, v in r.items()} for r in all_results.get("exp1_cross_scale", [])],
        "exp2_multi_target": [{k: v for k, v in r.items()} for r in all_results.get("exp2_multi_target", [])],
        "exp3_repeated": [{k: v for k, v in r.items()} for r in all_results.get("exp3_repeated", [])],
    }

    out_path = RESULTS_DIR / "ablation_suite.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False, default=str))
    logger.info(f"\nFull results saved to {out_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
