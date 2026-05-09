"""V1 Multi-Defect Ablation: Type A / B / C injections, all parallel.

Uses the EXISTING clean baseline from validation_suite.json (V1_ablation).
Each defect group runs independently — full concurrency across groups.
Within each group, injections run with semaphore(2) for API safety.
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
from src.models.graph import DependencyGraph
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.alphago_mcgs import AlphaGoMCGS

from experiments.perturbation import perturb_type_a, perturb_type_b, perturb_type_c

RESULTS_DIR = Path("experiments/results")

TYPE_A_TARGETS = [
    "bgb_327o", "bgb_312", "bgb_507", "bgb_505",
    "bgb_358", "bgb_504", "bgb_327", "bgb_506",
]

TYPE_B_PAIRS = [
    ("bgb_327o", "bgb_327"),
    ("bgb_312", "bgb_507"),
    ("bgb_505", "bgb_504"),
    ("bgb_358", "bgb_506"),
]

TYPE_C_EXTRA = [
    "bgb_360", "bgb_508", "bgb_491", "bgb_312f",
]


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
        "ucb_exploration_init": 2.5, "virtual_loss_weight": 3,
        "temperature": 0.3, "max_tokens": 2048,
        "tt_max_reuse": 3, "dirichlet_alpha": 0.3,
        "dirichlet_weight": 0.25,
    }
    ag_config["detection"] = {"alpha": 0.1, "min_rollouts": 8}

    mcgs = AlphaGoMCGS(llm_client, ag_config)
    return await mcgs.search(graph, scc_info)


async def run_single(llm_client, graph, config, scc_ids, sem,
                     label, perturb_fn, idx, total):
    """Run one injection: perturb -> MCGS -> extract subgraph."""
    async with sem:
        logger.info(f"  [{idx}/{total}] {label} — starting ...")
        t0 = time.monotonic()
        try:
            pg = perturb_fn()
            DomainGraphPruner(config).prune(pg)
            pg = TarjanSCCDetector().detect(pg)
            pert_scc = next(
                (s for s in pg.sccs if any(c in s.clause_ids for c in scc_ids)),
                None,
            )
            if not pert_scc:
                logger.warning(f"  [{idx}] {label} — SCC not found after perturbation")
                return None

            result = await run_mcgs(llm_client, pg, config, pert_scc)
            elapsed = time.monotonic() - t0

            oc = set(result["oc_detected_clauses"])
            victims = pick_victims(oc, result["ranking_by_risk"])
            sg_nodes, sg_size = extract_subgraph(
                victims, result.get("edge_details", {}), list(scc_ids)
            )

            logger.info(
                f"  [{idx}] {label} done ({elapsed:.0f}s) — "
                f"OC={len(oc)}, SG={sg_size}/{len(scc_ids)}"
            )
            return {
                "label": label,
                "oc_detected": sorted(oc),
                "oc_count": len(oc),
                "subgraph_nodes": sg_nodes,
                "subgraph_size": sg_size,
                "risk_top5": [(c, round(s, 4)) for c, s in result["ranking_by_risk"][:5]],
                "time": round(elapsed, 1),
            }
        except Exception as e:
            logger.error(f"  [{idx}] {label} failed: {e}")
            return None


async def main():
    logger.info("=" * 70)
    logger.info("V1 MULTI-DEFECT ABLATION — Type A / B / C, fully parallel")
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

    scc_24 = next(s for s in graph.sccs if "bgb_327o" in s.clause_ids)
    scc_ids = list(scc_24.clause_ids)
    n = len(scc_ids)

    # Load existing clean baseline
    vs_path = RESULTS_DIR / "validation_suite.json"
    with open(vs_path) as f:
        vs = json.load(f)
    v1_clean = vs["V1_ablation"]
    clean_oc = set(v1_clean["clean_oc"])
    clean_sg_size = v1_clean["clean_subgraph_size"]
    clean_sg_nodes = set(v1_clean["clean_subgraph_nodes"])
    logger.info(f"Clean baseline loaded: OC={sorted(clean_oc)}, SG={clean_sg_size}/{n}")

    # Build all tasks
    sem = asyncio.Semaphore(3)
    tasks = []
    idx = 0

    for tid in TYPE_A_TARGETS:
        idx += 1
        tasks.append(run_single(
            llm_client, graph, config, scc_ids, sem,
            label=f"TypeA:{tid}",
            perturb_fn=lambda t=tid: perturb_type_a(graph, t),
            idx=idx, total=len(TYPE_A_TARGETS) + len(TYPE_B_PAIRS) + len(TYPE_C_EXTRA),
        ))

    for cx, cy in TYPE_B_PAIRS:
        idx += 1
        tasks.append(run_single(
            llm_client, graph, config, scc_ids, sem,
            label=f"TypeB:{cx}+{cy}",
            perturb_fn=lambda x=cx, y=cy: perturb_type_b(graph, scc_ids, x, y),
            idx=idx, total=len(TYPE_A_TARGETS) + len(TYPE_B_PAIRS) + len(TYPE_C_EXTRA),
        ))

    for tid in TYPE_C_EXTRA:
        idx += 1
        tasks.append(run_single(
            llm_client, graph, config, scc_ids, sem,
            label=f"TypeC:{tid}",
            perturb_fn=lambda t=tid: perturb_type_c(graph, scc_ids, t),
            idx=idx, total=len(TYPE_A_TARGETS) + len(TYPE_B_PAIRS) + len(TYPE_C_EXTRA),
        ))

    logger.info(f"\nLaunching {len(tasks)} injections (sem=3) ...")
    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r is not None]

    # Compare with clean baseline
    print("\n" + "=" * 115)
    print("V1 MULTI-DEFECT ABLATION RESULTS")
    print("=" * 115)
    print(f"Clean Baseline: OC={sorted(clean_oc)}, SG={clean_sg_size}/{n}")
    print()
    print(f"{'#':>2} {'Label':<22} | {'OC':>3} | {'NewOC':>5} | "
          f"{'SG':>6} | {'Expand':>6} | {'Time':>5} | Verdict")
    print("-" * 115)

    type_stats = {"A": [], "B": [], "C": []}
    for i, r in enumerate(results):
        pert_oc = set(r["oc_detected"])
        new_oc = pert_oc - clean_oc
        expansion = r["subgraph_size"] - clean_sg_size
        has_signal = len(new_oc) > 0 or expansion > 3
        verdict = "SIGNAL" if has_signal else "weak"

        ptype = r["label"].split(":")[0][-1]
        type_stats[ptype].append({
            "expansion": expansion, "new_oc": len(new_oc), "signal": has_signal
        })

        print(
            f"{i+1:>2} {r['label']:<22} | "
            f"{r['oc_count']:>3} | "
            f"{len(new_oc):>5} | "
            f"{r['subgraph_size']:>3}/{n:<2} | "
            f"{expansion:>+5} | "
            f"{r['time']:>4.0f}s | "
            f"{verdict}"
        )

    print("-" * 115)
    print("\nPER-TYPE SUMMARY:")
    for ptype in ["A", "B", "C"]:
        stats = type_stats[ptype]
        if not stats:
            continue
        sig = sum(1 for s in stats if s["signal"])
        avg_exp = sum(s["expansion"] for s in stats) / len(stats)
        avg_new_oc = sum(s["new_oc"] for s in stats) / len(stats)
        print(f"  Type {ptype}: {len(stats)} injections | "
              f"Signal: {sig}/{len(stats)} ({sig/len(stats):.0%}) | "
              f"Avg expand: +{avg_exp:.1f} | "
              f"Avg new OC: {avg_new_oc:.1f}")

    total_sig = sum(1 for r in results
                    for _ in [1]
                    if len(set(r["oc_detected"]) - clean_oc) > 0
                    or r["subgraph_size"] - clean_sg_size > 3)
    print(f"\n  OVERALL: {len(results)} injections | "
          f"Signal: {total_sig}/{len(results)} ({total_sig/len(results):.0%})")

    # Save
    out = {
        "method": "V1_multi_defect",
        "clean_baseline": {
            "oc": sorted(clean_oc),
            "sg_size": clean_sg_size,
            "sg_nodes": sorted(clean_sg_nodes),
        },
        "results": results,
        "per_type": {
            ptype: {
                "count": len(stats),
                "signal_count": sum(1 for s in stats if s["signal"]),
                "avg_expansion": round(sum(s["expansion"] for s in stats) / max(1, len(stats)), 1),
            }
            for ptype, stats in type_stats.items()
        },
    }
    out_path = RESULTS_DIR / "v1_multi_defect.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to {out_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
