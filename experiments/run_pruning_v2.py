"""Pruning V2: Plan A / B / C + baselines — 7 configs × 6 injections × 3 repeats = 126 runs.

All parallel (sem=4).

Configs:
  1. None (baseline, no pruning)
  2. Legacy (Noise + Hierarchy + IB)
  3. TACS_orig (original TACS — known to over-prune on homogeneous edges)
  4. PlanA_ETE+TACS (enrich edge types first, then type-aware prune)
  5. PlanB_Adaptive (topology-based fallback when types are homogeneous, with budget)
  6. PlanC_Soft (reweight edges by cycle saliency, no deletion)
  7. PlanAB_ETE+Adapt (combined: enrich + adaptive topology)

Injections (6):
  TypeC:327o, TypeA:506, TypeB:505+504, TypeA:358, TypeC:512, Clean

Each combination repeated 3 times → 126 experiments total.
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

NUM_REPEATS = 3

PRUNING_CONFIGS = {
    "None": {"enabled": False},
    "Legacy": {
        "enabled": True, "mode": "legacy",
        "noise_weight_threshold": 0.35, "remove_duplicate_reasoning": True,
        "hierarchy_violation_threshold": 0.6, "ib_compression_ratio": 0.15,
    },
    "TACS_orig": {
        "enabled": True, "mode": "new",
        "fgc_enabled": False, "tacs_enabled": True,
        "tacs_saliency_threshold": 0.4,
    },
    "PlanA_ETE+TACS": {
        "enabled": True, "mode": "plan_a",
        "ete_enabled": True,
        "tacs_enabled": True, "tacs_saliency_threshold": 0.4,
    },
    "PlanB_Adaptive": {
        "enabled": True, "mode": "plan_b",
        "adaptive_tacs_enabled": True,
        "adaptive_tacs_max_removal": 0.35,
        "adaptive_tacs_homogeneity": 0.80,
    },
    "PlanC_Soft": {
        "enabled": True, "mode": "plan_c",
        "soft_tacs_enabled": True,
        "soft_tacs_decay": 0.5,
    },
    "PlanAB_ETE+Adapt": {
        "enabled": True, "mode": "plan_a_tacs",
        "ete_enabled": True,
        "adaptive_tacs_enabled": True,
        "adaptive_tacs_max_removal": 0.35,
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
                  pruning_name, pruning_cfg, inject_label, inject_fn,
                  repeat_idx, sem):
    label = f"{pruning_name}|{inject_label}|R{repeat_idx}"
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
                logger.warning(f"[SKIP] {label}: SCC dissolved after pruning")
                return {"label": label, "pruning": pruning_name,
                        "injection": inject_label, "repeat": repeat_idx,
                        "error": "SCC_dissolved"}

            scc_set = set(target_scc.clause_ids)
            n_nodes = len(target_scc.clause_ids)
            n_edges = sum(1 for e in pg.edges
                          if e.source in scc_set and e.target in scc_set)

            result = await run_mcgs(llm_client, pg, full_config, target_scc)
            elapsed = time.monotonic() - t0

            oc = set(result["oc_detected_clauses"])
            victims = pick_victims(oc, result["ranking_by_risk"])
            sg_nodes, sg_size = extract_subgraph(
                victims, result.get("edge_details", {}),
                list(target_scc.clause_ids),
            )

            logger.info(f"[DONE] {label} ({elapsed:.0f}s) — "
                        f"N={n_nodes}, E={n_edges}, OC={len(oc)}, SG={sg_size}")

            return {
                "label": label, "pruning": pruning_name,
                "injection": inject_label, "repeat": repeat_idx,
                "scc_nodes": n_nodes, "scc_edges": n_edges,
                "oc_count": len(oc), "oc_detected": sorted(oc),
                "subgraph_size": sg_size, "subgraph_nodes": sg_nodes,
                "avg_risk": round(
                    sum(s for _, s in result["ranking_by_risk"]) / max(n_nodes, 1), 4),
                "top5_risk": [(c, round(s, 4))
                              for c, s in result["ranking_by_risk"][:5]],
                "llm_calls": result.get("llm_calls", 0),
                "time": round(elapsed, 1),
                "prune_stats": prune_stats,
            }
        except Exception as e:
            logger.error(f"[FAIL] {label}: {e}")
            return {"label": label, "pruning": pruning_name,
                    "injection": inject_label, "repeat": repeat_idx,
                    "error": str(e)}


async def main():
    total_runs = len(PRUNING_CONFIGS) * 6 * NUM_REPEATS
    logger.info("=" * 80)
    logger.info(f"PRUNING V2: {len(PRUNING_CONFIGS)} configs × 6 injections "
                f"× {NUM_REPEATS} repeats = {total_runs} experiments (sem=4)")
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
        "TypeC:327o":  lambda: perturb_type_c(graph, scc_ids, "bgb_327o"),
        "TypeA:506":   lambda: perturb_type_a(graph, "bgb_506"),
        "TypeB:505+4": lambda: perturb_type_b(graph, scc_ids, "bgb_505", "bgb_504"),
        "TypeA:358":   lambda: perturb_type_a(graph, "bgb_358"),
        "TypeC:512":   lambda: perturb_type_c(graph, scc_ids, "bgb_512"),
        "Clean":       lambda: graph.model_copy(deep=True),
    }

    sem = asyncio.Semaphore(4)
    tasks = []
    for repeat in range(1, NUM_REPEATS + 1):
        for pname, pcfg in PRUNING_CONFIGS.items():
            for iname, ifn in injections.items():
                tasks.append(run_one(
                    llm_client, graph, config, scc_ids,
                    pname, pcfg, iname, ifn, repeat, sem,
                ))

    logger.info(f"Launching {len(tasks)} experiments (sem=4)...")
    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r is not None]

    # ── Save raw results first ──
    out_path = RESULTS_DIR / "pruning_v2.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    logger.info(f"Raw results → {out_path}")

    # ── Print full per-run table ──
    n = len(scc_ids)
    ok_results = [r for r in results if "error" not in r]
    err_results = [r for r in results if "error" in r]

    print("\n" + "=" * 160)
    print(f"PRUNING V2 — ALL {len(results)} RUNS ({len(ok_results)} ok, {len(err_results)} errors)")
    print("=" * 160)
    print(f"{'Pruning':<18} {'Injection':<14} {'R':>1} | {'N':>3} {'E':>3} | "
          f"{'OC':>3} {'SG':>6} | {'AvgR':>6} | {'LLM':>4} | {'Time':>6}")
    print("-" * 160)

    for r in sorted(ok_results, key=lambda x: (x["pruning"], x["injection"], x["repeat"])):
        print(f"{r['pruning']:<18} {r['injection']:<14} {r['repeat']:>1} | "
              f"{r['scc_nodes']:>3} {r['scc_edges']:>3} | "
              f"{r['oc_count']:>3} {r['subgraph_size']:>3}/{n:<2} | "
              f"{r['avg_risk']:>6.4f} | "
              f"{r.get('llm_calls', '?'):>4} | "
              f"{r['time']:>5.0f}s")

    if err_results:
        print(f"\n--- ERRORS ({len(err_results)}) ---")
        for r in err_results:
            print(f"  {r.get('pruning','?')}|{r.get('injection','?')}|R{r.get('repeat','?')}: {r['error']}")

    # ── Aggregated averages: per (pruning, injection) across 3 repeats ──
    print("\n" + "=" * 160)
    print(f"AGGREGATED AVERAGES (mean ± across {NUM_REPEATS} repeats)")
    print("=" * 160)
    print(f"{'Pruning':<18} {'Injection':<14} | {'N':>3} {'E':>3} | "
          f"{'OC':>7} {'SG':>9} | {'AvgRisk':>8} | {'AvgTime':>7}")
    print("-" * 160)

    agg: dict[tuple[str, str], list] = defaultdict(list)
    for r in ok_results:
        agg[(r["pruning"], r["injection"])].append(r)

    for (pname, iname) in sorted(agg.keys()):
        runs = agg[(pname, iname)]
        k = len(runs)
        avg_n = sum(r["scc_nodes"] for r in runs) / k
        avg_e = sum(r["scc_edges"] for r in runs) / k
        avg_oc = sum(r["oc_count"] for r in runs) / k
        min_oc = min(r["oc_count"] for r in runs)
        max_oc = max(r["oc_count"] for r in runs)
        avg_sg = sum(r["subgraph_size"] for r in runs) / k
        min_sg = min(r["subgraph_size"] for r in runs)
        max_sg = max(r["subgraph_size"] for r in runs)
        avg_risk = sum(r["avg_risk"] for r in runs) / k
        avg_t = sum(r["time"] for r in runs) / k
        print(f"{pname:<18} {iname:<14} | {avg_n:>3.0f} {avg_e:>3.0f} | "
              f"{avg_oc:>4.1f}({min_oc}-{max_oc}) "
              f"{avg_sg:>4.1f}({min_sg}-{max_sg}) | "
              f"{avg_risk:>8.4f} | {avg_t:>6.0f}s")

    # ── Per-config summary (injection-only) ──
    print("\n" + "=" * 130)
    print("PER-CONFIG SUMMARY (injection runs only, excluding Clean)")
    print("=" * 130)
    print(f"{'Config':<18} | {'AvgN':>4} {'AvgE':>4} | {'AvgOC':>6} {'AvgSG':>6} | "
          f"{'AvgTime':>7} | {'Signal%':>8} | {'SCC_OK%':>7}")
    print("-" * 130)

    for pname in PRUNING_CONFIGS:
        inj_runs = [r for r in ok_results
                     if r["pruning"] == pname and r["injection"] != "Clean"]
        all_runs_for_p = [r for r in results
                          if r.get("pruning") == pname and r.get("injection") != "Clean"]
        if not inj_runs:
            scc_ok_pct = 0
            if all_runs_for_p:
                scc_ok_pct = len(inj_runs) / len(all_runs_for_p) * 100
            print(f"{pname:<18} | ---- ---- | ------ ------ | ------  | "
                  f"------  | {scc_ok_pct:>5.0f}%")
            continue

        k = len(inj_runs)
        avg_n = sum(r["scc_nodes"] for r in inj_runs) / k
        avg_e = sum(r["scc_edges"] for r in inj_runs) / k
        avg_oc = sum(r["oc_count"] for r in inj_runs) / k
        avg_sg = sum(r["subgraph_size"] for r in inj_runs) / k
        avg_t = sum(r["time"] for r in inj_runs) / k
        signal_pct = sum(1 for r in inj_runs if r["oc_count"] > 0) / k * 100
        scc_ok_pct = k / len(all_runs_for_p) * 100 if all_runs_for_p else 100

        print(f"{pname:<18} | {avg_n:>4.0f} {avg_e:>4.0f} | {avg_oc:>6.1f} {avg_sg:>5.1f}/{n:<2} | "
              f"{avg_t:>6.0f}s | {signal_pct:>6.0f}% | {scc_ok_pct:>5.0f}%")

    # ── Clean baseline ──
    print("\n" + "=" * 80)
    print("CLEAN BASELINE")
    print("=" * 80)
    for pname in PRUNING_CONFIGS:
        clean_runs = [r for r in ok_results
                      if r["pruning"] == pname and r["injection"] == "Clean"]
        if clean_runs:
            avg_oc = sum(r["oc_count"] for r in clean_runs) / len(clean_runs)
            avg_sg = sum(r["subgraph_size"] for r in clean_runs) / len(clean_runs)
            print(f"  {pname:<18}: AvgOC={avg_oc:.1f}, AvgSG={avg_sg:.1f}/{n} "
                  f"(×{len(clean_runs)} runs)")

    print(f"\nSaved {len(results)} results → {out_path}")
    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
