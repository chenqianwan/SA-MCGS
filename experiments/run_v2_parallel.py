"""V2 Multi-Injection: parallel execution across many injection points.

Each injection is independent, so we run them concurrently (2 at a time
to respect API rate limits). Covers hub, peripheral, high-risk, and
low-risk positions for comprehensive validation.
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
from src.models.graph import DependencyGraph, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.alphago_mcgs import AlphaGoMCGS

from experiments.perturbation import perturb_type_c

RESULTS_DIR = Path("experiments/results")

INJECT_TARGETS = [
    # Already tested (will merge with previous results)
    # "bgb_327o", "bgb_312", "bgb_505", "bgb_358",
    # New: hubs (high visit count / high connectivity)
    "bgb_327",    # central hub, 136 visits
    "bgb_312g",   # high connectivity
    # New: high risk nodes
    "bgb_507",    # risk #3
    "bgb_504",    # risk #5
    "bgb_506",    # risk #4
    # New: medium risk / middle tier
    "bgb_327m",   # medium risk
    "bgb_491a",   # high visit count
    "bgb_356",    # medium risk, diverse connectivity
    # New: low risk / peripheral
    "bgb_327b",   # low risk, peripheral
    "bgb_512",    # lowest risk node
    "bgb_515",    # second lowest risk
    "bgb_513",    # low-medium risk
]


def extract_subgraph(
    victims: set[str],
    edge_details: dict[str, dict],
    scc_ids: list[str],
    conflict_threshold: float = 0.3,
    max_hops: int = 3,
) -> dict:
    reverse_adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for _key, info in edge_details.items():
        src, tgt = info["source"], info["target"]
        if info["avg_conflict"] >= conflict_threshold:
            reverse_adj[tgt].append((src, info["avg_conflict"]))

    subgraph_nodes = set(victims)
    paths: list[list[str]] = []

    for victim in victims:
        queue: deque[tuple[str, list[str]]] = deque()
        queue.append((victim, [victim]))
        visited = {victim}
        while queue:
            node, path = queue.popleft()
            if len(path) > max_hops + 1:
                continue
            for upstream, _ in reverse_adj.get(node, []):
                if upstream in visited:
                    continue
                visited.add(upstream)
                new_path = path + [upstream]
                subgraph_nodes.add(upstream)
                if upstream not in victims:
                    paths.append(list(reversed(new_path)))
                queue.append((upstream, new_path))

    return {
        "nodes": sorted(subgraph_nodes),
        "size": len(subgraph_nodes),
        "paths": sorted(paths, key=len)[:10],
    }


async def run_single_injection(llm_client, graph, config, scc, target_id, idx, total):
    """Run one injection experiment."""
    logger.info(f"\n  --- [{idx}/{total}] Injection: {target_id} ---")
    t0 = time.monotonic()

    try:
        pg = perturb_type_c(graph, scc.clause_ids, target_id)
        DomainGraphPruner(config).prune(pg)
        pg = TarjanSCCDetector().detect(pg)
        pert_scc = next((s for s in pg.sccs if target_id in s.clause_ids), None)
        if not pert_scc:
            logger.warning(f"  SCC broken for {target_id}, skipping")
            return None

        n = len(pert_scc.clause_ids)
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
        result = await mcgs.search(pg, pert_scc)

        oc = set(result["oc_detected_clauses"])
        if oc:
            victims, src = oc, "oc"
        else:
            victims = {cid for cid, _ in result["ranking_by_risk"][:5]}
            src = "top_k"

        subgraph = extract_subgraph(
            victims, result.get("edge_details", {}), list(pert_scc.clause_ids)
        )

        target_hit = target_id in set(subgraph["nodes"])
        target_in_top5 = target_id in {cid for cid, _ in result["ranking_by_risk"][:5]}
        target_in_top10 = target_id in {cid for cid, _ in result["ranking_by_risk"][:10]}

        neighbors_in_subgraph = []
        for key, info in result.get("edge_details", {}).items():
            if info["source"] == target_id and info["target"] in set(subgraph["nodes"]):
                neighbors_in_subgraph.append(info["target"])
            if info["target"] == target_id and info["source"] in set(subgraph["nodes"]):
                neighbors_in_subgraph.append(info["source"])

        target_risk_rank = next(
            (i + 1 for i, (cid, _) in enumerate(result["ranking_by_risk"]) if cid == target_id),
            n
        )

        elapsed = time.monotonic() - t0
        near = target_hit or len(set(neighbors_in_subgraph)) >= 2

        logger.info(f"    [{target_id}] OC={len(oc)} victims({src})={len(victims)} "
                     f"SG={subgraph['size']}/{n} HIT={'Y' if target_hit else 'N'} "
                     f"Nbrs={len(neighbors_in_subgraph)} Rank=#{target_risk_rank} "
                     f"{'PASS' if near else 'MISS'} ({elapsed:.0f}s)")

        return {
            "target_id": target_id,
            "scc_size": n,
            "oc_detected": sorted(oc),
            "oc_count": len(oc),
            "victims": sorted(victims),
            "victim_source": src,
            "subgraph_nodes": subgraph["nodes"],
            "subgraph_size": subgraph["size"],
            "subgraph_paths": subgraph["paths"][:5],
            "target_hit": target_hit,
            "target_in_top5": target_in_top5,
            "target_in_top10": target_in_top10,
            "target_risk_rank": target_risk_rank,
            "target_neighbors_in_subgraph": list(set(neighbors_in_subgraph)),
            "near_hit": near,
            "llm_calls": result.get("llm_calls", 0),
            "time": elapsed,
        }

    except Exception as e:
        logger.error(f"  [{target_id}] failed: {e}")
        return None


async def main():
    logger.info("=" * 70)
    logger.info("V2 MULTI-INJECTION (PARALLEL) — 12 injection points")
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
    total = len(INJECT_TARGETS)

    # Run 2 at a time to respect rate limits while still parallelizing
    results = []
    sem = asyncio.Semaphore(2)

    async def bounded_run(tid, idx):
        async with sem:
            return await run_single_injection(
                llm_client, graph, config, scc_24, tid, idx, total
            )

    tasks = [bounded_run(tid, i + 1) for i, tid in enumerate(INJECT_TARGETS)]
    raw_results = await asyncio.gather(*tasks)
    results = [r for r in raw_results if r is not None]

    # Merge with previous V2 results
    prev_path = RESULTS_DIR / "validation_suite.json"
    if prev_path.exists():
        prev = json.load(open(prev_path))
        prev_injections = prev.get("V2_multi_inject", {}).get("injections", [])
        prev_ids = {r["target_id"] for r in results}
        for pr in prev_injections:
            if pr["target_id"] not in prev_ids:
                pr["near_hit"] = pr.get("target_hit", False) or len(pr.get("target_neighbors_in_subgraph", [])) >= 2
                pr["target_in_top10"] = pr.get("target_in_top5", False)
                pr["target_risk_rank"] = pr.get("target_risk_rank", "?")
                pr["oc_count"] = len(pr.get("oc_detected", []))
                results.append(pr)

    results.sort(key=lambda r: r["target_id"])

    # Summary
    print("\n" + "=" * 110)
    print("V2 MULTI-INJECTION — COMPREHENSIVE RESULTS")
    print("=" * 110)
    print(f"{'#':>2} {'Target':<12} | {'SG':>5} | {'HIT':>3} | {'Near':>4} | "
          f"{'#Nbrs':>5} | {'OC':>2} | {'Rank':>4} | {'Top5':>4} | {'Top10':>5} | {'Verdict'}")
    print("-" * 110)

    hits = 0
    nears = 0
    for i, r in enumerate(results):
        verdict = "PASS" if r["near_hit"] else "MISS"
        if r["near_hit"]:
            nears += 1
        if r.get("target_hit", False):
            hits += 1
        print(
            f"{i+1:>2} {r['target_id']:<12} | "
            f"{r['subgraph_size']:>2}/24 | "
            f"{'YES' if r.get('target_hit') else ' NO':>3} | "
            f"{'YES' if r['near_hit'] else ' NO':>4} | "
            f"{len(r.get('target_neighbors_in_subgraph', [])):>5} | "
            f"{r.get('oc_count', '?'):>2} | "
            f"#{r.get('target_risk_rank', '?'):>3} | "
            f"{'YES' if r.get('target_in_top5') else ' NO':>4} | "
            f"{'YES' if r.get('target_in_top10') else ' NO':>5} | "
            f"{verdict}"
        )

    n_total = len(results)
    print("-" * 110)
    print(f"TOTAL: {n_total} injections | "
          f"Direct HIT: {hits}/{n_total} ({hits/n_total:.0%}) | "
          f"Near HIT (hit or 2+ nbrs): {nears}/{n_total} ({nears/n_total:.0%})")

    # Breakdown by node position
    print(f"\nBy subgraph coverage:")
    avg_sg = sum(r["subgraph_size"] for r in results) / len(results)
    print(f"  Average subgraph size: {avg_sg:.1f}/24 ({avg_sg/24:.0%})")

    out_path = RESULTS_DIR / "v2_multi_inject_full.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"method": "V2_multi_inject_full", "total": n_total,
         "hit_rate": hits / max(1, n_total),
         "near_rate": nears / max(1, n_total),
         "injections": results},
        indent=2, ensure_ascii=False, default=str,
    ))
    print(f"\nSaved to {out_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
