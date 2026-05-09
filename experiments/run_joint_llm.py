"""Run Joint LLM evaluation for SCC cases.
This simulates the 'brute force' approach where all clauses in an SCC are 
evaluated in a single LLM call, without multiple sampling or MCGS search.
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
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.scc_sampler import SCCSampler
from src.models.clause import ClauseEvaluation
from experiments.runner import _run_direct_llm, ExperimentResult

async def run_joint_llm_experiment():
    logger.info("=" * 70)
    logger.info("R7_JOINT: Joint LLM (Full SCC in one call) Experiment")
    logger.info("=" * 70)

    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)
    
    llm_client = OpenAIClient(config["llm"])
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single("data/quantlaw/de/4_crossreference_graph/bgb_focus.gpickle.gz")

    # Load baseline for delta calculation
    baseline_path = Path("experiments/results/baseline_bgb_focus.json")
    baseline = json.loads(baseline_path.read_text())
    baseline_cr = baseline.get("clause_results", {})

    # Setup graph
    DomainGraphPruner(config).prune(graph)
    graph = TarjanSCCDetector().detect(graph)

    # Define the 6 SCC cases (same as R5/R6)
    cases = [
        {"target_id": "bgb_275", "ptype": "type_a"},
        {"target_id": "bgb_275", "ptype": "type_b"},
        {"target_id": "bgb_275", "ptype": "type_c"},
        {"target_id": "bgb_555c", "ptype": "type_a"},
        {"target_id": "bgb_555c", "ptype": "type_b"},
        {"target_id": "bgb_555c", "ptype": "type_c"},
    ]

    from experiments.perturbation import perturb_type_a, perturb_type_b, perturb_type_c, _ensure_clause_text
    
    results = []
    sampler = SCCSampler(llm_client, config)

    for case in cases:
        target_id = case["target_id"]
        ptype = case["ptype"]
        logger.info(f"Processing {target_id} ({ptype})...")

        # 1. Perturb
        if ptype == "type_a":
            perturbed_g = perturb_type_a(graph, target_id)
        elif ptype == "type_b":
            # Find SCC for target
            scc = next(s for s in graph.sccs if target_id in s.clause_ids)
            # Find another node in same SCC
            other = next(cid for cid in scc.clause_ids if cid != target_id)
            perturbed_g = perturb_type_b(graph, scc.clause_ids, target_id, other)
        elif ptype == "type_c":
            scc = next(s for s in graph.sccs if target_id in s.clause_ids)
            perturbed_g = perturb_type_c(graph, scc.clause_ids, target_id)
        
        # 2. Joint LLM Evaluation (Single Sample)
        # We use SCCSampler's internal logic but only for 1 sample
        scc_info = next(s for s in perturbed_g.sccs if target_id in s.clause_ids)
        clauses = [perturbed_g.clauses[cid] for cid in scc_info.clause_ids]
        use_compact = len(clauses) >= sampler.compact_threshold
        
        # Build prompt (no upstream context for simplicity/purity of 'joint' test)
        prompt = sampler._build_joint_prompt(clauses, scc_info.internal_edges, [], compact=use_compact)
        
        t0 = time.monotonic()
        # Use temp=0 for deterministic 'best' joint evaluation
        resp = await llm_client.call_json(prompt, temperature=0.0, max_tokens=sampler.max_tokens)
        elapsed = time.monotonic() - t0
        
        evals = sampler._parse_joint_evaluation(resp, scc_info.clause_ids, compact=use_compact)
        target_eval = evals.get(target_id)
        
        if not target_eval:
            logger.error(f"Failed to get evaluation for {target_id} in joint response")
            continue
            
        score = target_eval.overall_risk_score
        # Detection logic: same as MCGS (score >= 0.7)
        detected = score >= 0.7
        
        # 3. Direct LLM (Single Clause) for comparison (reuse R3 data if possible, or re-run)
        clause = perturbed_g.clauses.get(target_id)
        text = _ensure_clause_text(clause, perturbed_g)
        llm_score, llm_detected, llm_time = await _run_direct_llm(llm_client, text, target_id)

        base_risk = baseline_cr.get(target_id, {}).get("mean_risk_score", 0.5)

        res = {
            "round": "R7_JOINT",
            "graph_id": "bgb_focus",
            "target_clause_id": target_id,
            "perturbation_type": ptype,
            "mcgs_risk_score": score, # We reuse the field for Joint LLM score
            "mcgs_high_risk_detected": detected,
            "direct_llm_risk_score": llm_score,
            "direct_llm_detected": llm_detected,
            "delta_mcgs_risk": score - base_risk,
            "delta_direct_llm_risk": llm_score - base_risk,
            "mcgs_time_seconds": elapsed,
            "direct_llm_time_seconds": llm_time,
            "joint_detected": detected,
            "config_name": "joint_llm"
        }
        results.append(res)
        logger.info(f"  Joint: {score:.3f} ({'✓' if detected else '✗'}), Direct: {llm_score:.3f}, Base: {base_risk:.3f}")

    # Merge into live_results.json
    live_path = Path("experiments/results/live_results.json")
    live_data = json.loads(live_path.read_text())
    
    # Remove old R7 if exists
    live_data = [r for r in live_data if r.get("round") != "R7_JOINT"]
    live_data.extend(results)
    
    live_path.write_text(json.dumps(live_data, indent=2, ensure_ascii=False))
    logger.info(f"Saved {len(results)} R7_JOINT results to {live_path}")

    await llm_client.close()

if __name__ == "__main__":
    asyncio.run(run_joint_llm_experiment())
