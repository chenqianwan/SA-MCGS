"""Pruning Strategy Comparison: Legacy vs New (FGC + TACS).

Runs 5 pruning configurations × 4 injection scenarios = 20 experiments,
all in parallel (semaphore=3 for API safety).

Configurations:
  1. No Pruning (baseline)
  2. Legacy (Noise + Hierarchy + IB)
  3. FGC Only
  4. TACS Only
  5. FGC + TACS (new principled approach)

Injection scenarios:
  A. Type C on bgb_327o (stealthy, hardest)
  B. Type A on bgb_506 (semantic contradiction, strongest signal)
  C. Type B on bgb_505+bgb_504 (circular deadlock)
  D. Clean (no injection, baseline signal)
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict, deque
from pathlib import Path

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.alphago_mcgs import AlphaGoMCGS

from experiments.perturbation import perturb_type_a, perturb_type_b, perturb_type_c

RESULTS_DIR = Path("experiments/results")

PRUNING_CONFIGS = {
    "None": {"enabled": False},
    "Legacy": {
        "enabled": True, "mode": "legacy",
        "noise_weight_threshold": 0.35, "remove_duplicate_reasoning": True,
        "hierarchy_violation_threshold": 0.6, "ib_compression_ratio": 0.15,
    },
    "FGC": {
        "enabled": True, "mode": "new",
        "fgc_enabled": True, "tacs_enabled": False,
    },
    "TACS": {
        "enabled": True, "mode": "new",
        "fgc_enabled": False, "tacs_enabled": True,
        "tacs_saliency_threshold": 0.4, "tacs_max_cycle_length": 6,
    },
    "FGC+TACS": {
        "enabled": True, "mode": "new",
        "fgc_enabled": True, "tacs_enabled": True,
        "tacs_saliency_threshold": 0.4, "tacs_max_cycle_length": 6,
    },
}


def extract_subgraph(victims, edge_details, scc_ids,
                     conflict_threshold=0.3, max_hops=3):
    reverse_adj = defaultdict(list)
    for _key, info in edge_details.items():
        if info["avg_conflict"] >= conflict_threshold:
            reverse_adj[info["target"]].append(info["source"])
    subgraph_nodes = set(victims)
    for victim in victims:
        queue = deque([(victim, 0)])
        visited = {victim}
        while queue:
            node, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for upstream in reverse_adj.get(node, []):
                if upstream not in visited:
                    visited.add(upstream)
                    subgraph_nodes.add(upstream)
                    queue.append((upstream, depth + 1))
    return sorted(subgraph_nodes), len(subgraph_nodes)


def pick_victims(oc_detected, ranking, top_k=5):
    if oc_detected:
        return set(oc_detected)
    return {cid for cid, _ in ranking[:top_k]}


async def run_mcgs(llm_client, graph, config, scc_info):
    n = len(scc_info.clause_ids)
    budget = min(400, max(60, n * 15))
    window_size = min(5, max(3, n // 6))
    ag_config = json.loads(json.dumps(config))
    ag_config["alphago_mcgs"] = {
        "budget": budget, "window_size": window_size,
        "concurrency": 6, "ucb_exploration_weight": 1.414,
        "ucb_exploration_init": 2.5, "tt_max_reuse": 3,
        "dirichlet_alpha": 0.3, "dirichlet_weight": 0.25,
    }
    ag_config["detection"] = {"alpha": 0.1, "min_rollouts": 8}
    mcgs = AlphaGoMCGS(llm_client, ag_config)
    return await mcgs.search(graph, scc_info)


async def run_one(llm_client, base_graph, config, scc_ids,
                  pruning_name, pruning_cfg, inject_label, inject_fn, sem):
    label = f"{pruning_name}|{inject_label}"
    async with sem:
        logger.info(f"[START] {label}")
        t0 = time.monotonic()
        try:
            pg = inject_fn()
            full_config = json.loads(json.dumps(config))
            full_config["graph_pruning"] = pruning_cfg
            pruner = DomainGraphPruner(full_config)
            prune_stats = pruner.prune(pg)
            pg = TarjanSCCDetector().detect(pg)

            target_scc = next(
                (s for s in pg.sccs if any(c in s.clause_ids for c in scc_ids)),
                None,
            )
            if not target_scc:
                return {"label": label, "error": "SCC not found"}

            n_nodes = len(target_scc.clause_ids)
            n_edges = sum(
                1 for e in pg.edges
                if e.source in set(target_scc.clause_ids)
                and e.target in set(target_scc.clause_ids)
            )

            result = await run_mcgs(llm_client, pg, full_config, target_scc)
            elapsed = time.monotonic() - t0

            oc = set(result["oc_detected_clauses"])
            victims = pick_victims(oc, result["ranking_by_risk"])
            sg_nodes, sg_size = extract_subgraph(
                victims, result.get("edge_details", {}),
                list(target_scc.clause_ids),
            )

            logger.info(f"[DONE] {label} ({elapsed:.0f}s) — N={n_nodes}, E={n_edges}, OC={len(oc)}, SG={sg_size}")

            return {
                "label": label,
                "pruning": pruning_name,
                "injection": inject_label,
                "scc_nodes": n_nodes,
                "scc_edges": n_edges,
                "oc_count": len(oc),
                "oc_detected": sorted(oc),
                "subgraph_size": sg_size,
                "subgraph_nodes": sg_nodes,
                "avg_risk": round(sum(s for _, s in result["ranking_by_risk"]) / max(n_nodes, 1), 4),
                "top5_risk": [(c, round(s, 4)) for c, s in result["ranking_by_risk"][:5]],
                "llm_calls": result.get("llm_calls", 0),
                "time": round(elapsed, 1),
                "prune_stats": prune_stats,
            }
        except Exception as e:
            logger.error(f"[FAIL] {label}: {e}")
            return {"label": label, "error": str(e)}


async def main():
    logger.info("=" * 80)
    logger.info("PRUNING COMPARISON: 5 configs × 4 injections = 20 experiments")
    logger.info("=" * 80)

    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    llm_client = OpenAIClient(config["llm"])
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz"
    )
    graph = TarjanSCCDetector().detect(graph)
    scc_24 = next(s for s in graph.sccs if "bgb_327o" in s.clause_ids)
    scc_ids = list(scc_24.clause_ids)

    injections = {
        "TypeC:bgb_327o": lambda: perturb_type_c(graph, scc_ids, "bgb_327o"),
        "TypeA:bgb_506": lambda: perturb_type_a(graph, "bgb_506"),
        "TypeB:505+504": lambda: perturb_type_b(graph, scc_ids, "bgb_505", "bgb_504"),
        "Clean": lambda: graph.model_copy(deep=True),
    }

    sem = asyncio.Semaphore(3)
    tasks = []
    for pname, pcfg in PRUNING_CONFIGS.items():
        for iname, ifn in injections.items():
            tasks.append(run_one(
                llm_client, graph, config, scc_ids,
                pname, pcfg, iname, ifn, sem,
            ))

    logger.info(f"Launching {len(tasks)} experiments (sem=3)...")
    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r is not None]

    # Print summary
    n = len(scc_ids)
    print("\n" + "=" * 140)
    print("PRUNING COMPARISON — FULL RESULTS")
    print("=" * 140)
    print(f"{'Pruning':<12} {'Injection':<16} | {'N':>3} {'E':>3} | "
          f"{'OC':>3} {'SG':>6} | {'AvgRisk':>8} | {'LLM':>4} | {'Time':>6} | Notes")
    print("-" * 140)

    grouped: dict[str, list] = defaultdict(list)
    for r in results:
        if "error" in r:
            print(f"{r.get('pruning','?'):<12} {r.get('injection','?'):<16} | ERROR: {r['error']}")
            continue
        grouped[r["pruning"]].append(r)
        print(
            f"{r['pruning']:<12} {r['injection']:<16} | "
            f"{r['scc_nodes']:>3} {r['scc_edges']:>3} | "
            f"{r['oc_count']:>3} {r['subgraph_size']:>3}/{n:<2} | "
            f"{r['avg_risk']:>8.4f} | "
            f"{r.get('llm_calls', '?'):>4} | "
            f"{r['time']:>5.0f}s |"
        )

    # Per-config summary
    print("\n" + "=" * 100)
    print("PER-CONFIG AVERAGES (injection runs only, excluding Clean)")
    print("=" * 100)
    print(f"{'Config':<12} | {'Avg N':>5} {'Avg E':>5} | {'Avg OC':>6} {'Avg SG':>6} | {'Avg Time':>8}")
    print("-" * 100)
    for pname in PRUNING_CONFIGS:
        runs = [r for r in grouped.get(pname, []) if r["injection"] != "Clean"]
        if not runs:
            continue
        avg_n = sum(r["scc_nodes"] for r in runs) / len(runs)
        avg_e = sum(r["scc_edges"] for r in runs) / len(runs)
        avg_oc = sum(r["oc_count"] for r in runs) / len(runs)
        avg_sg = sum(r["subgraph_size"] for r in runs) / len(runs)
        avg_t = sum(r["time"] for r in runs) / len(runs)
        print(f"{pname:<12} | {avg_n:>5.1f} {avg_e:>5.1f} | {avg_oc:>6.1f} {avg_sg:>5.1f}/{n:<2} | {avg_t:>7.0f}s")

    # Clean baseline comparison
    print("\n" + "=" * 100)
    print("CLEAN BASELINE (no injection) — should have minimal signal")
    print("=" * 100)
    for r in results:
        if "error" not in r and r.get("injection") == "Clean":
            print(f"  {r['pruning']:<12}: N={r['scc_nodes']}, E={r['scc_edges']}, "
                  f"OC={r['oc_count']}, SG={r['subgraph_size']}/{n}")

    out_path = RESULTS_DIR / "pruning_comparison.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to {out_path}")
    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
