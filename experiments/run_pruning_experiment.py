"""Pruning Ablation Experiment: Evaluate the impact of the 3 pruning strategies.

Focus on the complex 24n SCC and target bgb_327o (Type C).
Compares:
1. No Pruning
2. Noise Removal Only
3. Noise + Hierarchical Prior
4. Full Pruning (Noise + Hierarchy + Info Bottleneck)
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
from src.modules.alphago_mcgs import AlphaGoMCGS
from experiments.perturbation import perturb_type_c

RESULTS_DIR = Path("experiments/results")

TARGET_ID = "bgb_327o"


async def run_mcgs(llm_client, graph, config, scc_info):
    n = len(scc_info.clause_ids)
    budget = min(400, max(60, n * 15))
    window_size = min(5, max(3, n // 6))

    ag_config = json.loads(json.dumps(config))
    ag_config["alphago_mcgs"] = {
        "budget": budget,
        "window_size": window_size,
        "concurrency": 6,
        "ucb_exploration_weight": 1.414,
        "ucb_exploration_init": 2.5,
        "tt_max_reuse": 3,
        "dirichlet_alpha": 0.3,
        "dirichlet_weight": 0.25,
    }
    ag_config["detection"] = {"alpha": 0.1, "min_rollouts": 8}

    mcgs = AlphaGoMCGS(llm_client, ag_config)
    return await mcgs.search(graph, scc_info)


async def run_one_config(llm_client, base_graph, config, pruner_cfg, label, sem):
    logger.info(f"\n>>> CONFIG: {label} <<<")
    async with sem:
        # 1. Apply perturbation
        scc_24_ids = next(s for s in base_graph.sccs if TARGET_ID in s.clause_ids).clause_ids
        pg = perturb_type_c(base_graph, scc_24_ids, TARGET_ID)

        # 2. Apply pruning
        full_config = json.loads(json.dumps(config))
        full_config["graph_pruning"] = pruner_cfg
        
        t0 = time.monotonic()
        pruner = DomainGraphPruner(full_config)
        prune_stats = pruner.prune(pg)
        
        # 3. Detect SCCs after pruning
        pg = TarjanSCCDetector().detect(pg)
        pert_scc = next((s for s in pg.sccs if TARGET_ID in s.clause_ids), None)
        
        if not pert_scc:
            return {"label": label, "error": "SCC disappeared after pruning"}

        n_nodes = len(pert_scc.clause_ids)
        n_edges = len([e for e in pg.edges if e.source in pert_scc.clause_ids and e.target in pert_scc.clause_ids])
        logger.info(f"Post-pruning SCC: nodes={n_nodes}, edges={n_edges}")

        # 4. Search
        result = await run_mcgs(llm_client, pg, full_config, pert_scc)
        elapsed = time.monotonic() - t0
        
        oc_count = len(result["oc_detected_clauses"])
        return {
            "label": label,
            "prune_stats": prune_stats,
            "scc_nodes": n_nodes,
            "scc_edges": n_edges,
            "oc_count": oc_count,
            "time": round(elapsed, 1),
            "avg_risk": round(sum(s for _, s in result["ranking_by_risk"]) / n_nodes, 4),
            "top_risk": result["ranking_by_risk"][0],
        }


async def main():
    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    llm_client = OpenAIClient(config["llm"])
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single("data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz")
    # Initial detect to find the 24n SCC
    graph = TarjanSCCDetector().detect(graph)

    configs = [
        ("Baseline (None)", {"enabled": False}),
        ("Noise Only", {"enabled": True, "noise_weight_threshold": 0.35, "remove_duplicate_reasoning": True, 
                        "hierarchy_violation_threshold": 0.0, "ib_compression_ratio": 0.0}),
        ("Noise + Hierarchy", {"enabled": True, "noise_weight_threshold": 0.35, "remove_duplicate_reasoning": True, 
                               "hierarchy_violation_threshold": 0.6, "ib_compression_ratio": 0.0}),
        ("Full (SA-MCGS)", {"enabled": True, "noise_weight_threshold": 0.35, "remove_duplicate_reasoning": True, 
                            "hierarchy_violation_threshold": 0.6, "ib_compression_ratio": 0.15}),
    ]

    # Build all tasks with a semaphore for API safety
    sem = asyncio.Semaphore(2)
    
    tasks = []
    for label, pcfg in configs:
        tasks.append(run_one_config(llm_client, graph, config, pcfg, label, sem))

    logger.info(f"Launching {len(tasks)} pruning configurations in parallel (sem=2)...")
    all_results = await asyncio.gather(*tasks)

    print("\n" + "=" * 100)
    print("PRUNING ABLATION SUMMARY")
    print("=" * 100)
    print(f"{'Config':<20} | {'SCC N':>5} | {'SCC E':>5} | {'OC':>3} | {'AvgRisk':>8} | {'Time':>6}")
    print("-" * 100)
    for r in all_results:
        if "error" in r:
            print(f"{r['label']:<20} | ERROR: {r['error']}")
            continue
        print(f"{r['label']:<20} | {r['scc_nodes']:>5} | {r['scc_edges']:>5} | "
              f"{r['oc_count']:>3} | {r['avg_risk']:>8.4f} | {r['time']:>5.0f}s")
    
    out_path = RESULTS_DIR / "pruning_experiment.json"
    out_path.write_text(json.dumps(all_results, indent=2))
    print(f"\nSaved to {out_path}")
    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
