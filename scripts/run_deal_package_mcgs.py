"""Run SA-MCGS on merged deal-package graphs to test subgraph localization.

Key question: can MCGS narrow from a 10-13 node SCC to a 5-7 node subgraph?
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm import OpenAIClient
from src.models.graph import DependencyGraph, Edge, DependencyType, SCCInfo
from src.models.clause import Clause
from src.modules.tarjan import TarjanSCCDetector
from src.modules.alphago_mcgs import AlphaGoMCGS
from experiments.run_clause_battle import add_medium_implicit_edges
from scripts.analyze_deal_packages import (
    merge_graphs, add_cross_contract_edges, FG_DIR, DEAL_PACKAGES,
)
from src.data.cuad_loader import CUADLoader
from experiments.perturbation import perturb_type_a

NUM_REPEATS = 3
CONCURRENCY = 4

TARGETS = [
    "AzulSa (2xMaintenance)",
    "Reynolds (Supply+Service)",
    "NETGEAR (Distributor+2Amend)",
]


def load_and_merge(pkg_name: str) -> DependencyGraph | None:
    loader = CUADLoader(str(FG_DIR.parent), config={"cuad": {"clause_only": False}})
    files = DEAL_PACKAGES[pkg_name]
    graphs = []
    for fname in files:
        fpath = FG_DIR / fname
        result = loader.load_single_graph(fpath)
        if result:
            graphs.append(result)
    if len(graphs) < 2:
        return None
    merged = merge_graphs(graphs)
    cross = add_cross_contract_edges(merged)
    merged.edges.extend(cross)
    merged = add_medium_implicit_edges(merged)
    merged = TarjanSCCDetector().detect(merged)
    return merged


def pick_victims(oc_detected, ranking, top_k=5):
    if oc_detected:
        return set(oc_detected)
    return {cid for cid, _ in ranking[:top_k]}


def extract_subgraph(victims, edge_details, scc_ids, conflict_threshold=0.3, max_hops=3):
    from collections import deque
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


async def run_mcgs(llm_client, graph, config, scc_info):
    n = len(scc_info.clause_ids)
    budget = min(400, max(60, n * 15))
    window_size = min(5, max(3, n // 5))
    ag_config = json.loads(json.dumps(config))
    ag_config["alphago_mcgs"] = {
        "budget": budget, "window_size": window_size,
        "concurrency": 4, "ucb_exploration_weight": 1.414,
        "ucb_exploration_init": 2.5, "tt_max_reuse": 3,
        "dirichlet_alpha": 0.3, "dirichlet_weight": 0.25,
    }
    ag_config["detection"] = {"alpha": 0.1, "min_rollouts": 8}
    mcgs = AlphaGoMCGS(llm_client, ag_config)
    return await mcgs.search(graph, scc_info)


async def run_one(llm_client, graph, config, scc, label, target_id, sem):
    async with sem:
        print(f"[START] {label} (SCC={scc.size})")
        t0 = time.monotonic()
        try:
            result = await run_mcgs(llm_client, graph, config, scc)
            elapsed = time.monotonic() - t0

            oc = set(result.get("oc_detected_clauses", []))
            ranking = result.get("ranking_by_risk", [])
            victims = pick_victims(list(oc), ranking)
            sg_nodes, sg_size = extract_subgraph(
                victims, result.get("edge_details", {}), list(scc.clause_ids),
            )

            target_hit = target_id in sg_nodes if target_id else False
            target_in_oc = target_id in oc if target_id else False
            ranked_ids = [cid for cid, _ in ranking]
            target_rank = ranked_ids.index(target_id) + 1 if target_id and target_id in ranked_ids else -1

            ratio = sg_size / scc.size if scc.size > 0 else 1.0

            print(f"[DONE] {label} ({elapsed:.0f}s) — "
                  f"SCC={scc.size} -> SG={sg_size} (ratio={ratio:.1%}), "
                  f"OC={len(oc)}, target_hit={target_hit}, target_rank={target_rank}")

            return {
                "label": label, "scc_size": scc.size, "subgraph_size": sg_size,
                "ratio": round(ratio, 3), "oc_count": len(oc),
                "target_id": target_id, "target_hit": target_hit,
                "target_in_oc": target_in_oc, "target_rank": target_rank,
                "top5": [(c, round(s, 4)) for c, s in ranking[:5]],
                "subgraph_nodes": sg_nodes,
                "time": round(elapsed, 1),
            }
        except Exception as e:
            print(f"[FAIL] {label}: {e}")
            import traceback; traceback.print_exc()
            return {"label": label, "error": str(e)}


async def main():
    os.environ["XHUB_API_KEY"] = os.environ.get("XHUB_API_KEY", "")
    config = {
        "llm": {
            "provider": "openai", "model": "deepseek-chat",
            "base_url": "https://api3.xhub.chat/v1",
            "api_key_env": "XHUB_API_KEY",
            "max_concurrent_calls": 8, "timeout": 120,
        }
    }
    llm_client = OpenAIClient(config["llm"])
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = []

    for pkg_name in TARGETS:
        print(f"\n{'='*80}")
        print(f"Loading {pkg_name}...")
        graph = load_and_merge(pkg_name)
        if not graph or not graph.sccs:
            print(f"  No SCCs, skip")
            continue

        best_scc = max(graph.sccs, key=lambda s: s.size)
        print(f"  Total nodes: {len(graph.clauses)}, Best SCC: {best_scc.size} nodes")
        print(f"  SCC members: {best_scc.clause_ids[:10]}...")

        # --- Clean runs ---
        for r in range(1, NUM_REPEATS + 1):
            tasks.append(run_one(
                llm_client, graph, config, best_scc,
                f"{pkg_name}|Clean|R{r}", None, sem,
            ))

        # --- Poisoned runs (Type A on random SCC member) ---
        import random
        random.seed(42)
        poison_targets = random.sample(best_scc.clause_ids, min(3, len(best_scc.clause_ids)))

        for tidx, target_id in enumerate(poison_targets):
            poisoned = graph.model_copy(deep=True)
            clause = poisoned.clauses[target_id]
            original_text = clause.content or clause.title or "provision"
            clause.metadata["_original_content"] = original_text
            clause.content = (
                f"{original_text} "
                f"Notwithstanding the foregoing, the exact opposite shall apply and "
                f"all obligations stated above are hereby nullified. "
                f"However, all nullified obligations remain binding and enforceable."
            )
            clause.metadata["_perturbed"] = "type_a"

            poisoned.sccs = graph.sccs
            for r in range(1, NUM_REPEATS + 1):
                tasks.append(run_one(
                    llm_client, poisoned, config, best_scc,
                    f"{pkg_name}|Poison_T{tidx}({target_id[:25]})|R{r}",
                    target_id, sem,
                ))

    print(f"\nTotal experiments: {len(tasks)}")
    print("Launching...\n")

    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r]

    out = Path("experiments/results/deal_package_mcgs.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))

    # Summary
    print("\n" + "=" * 100)
    print("DEAL PACKAGE SA-MCGS RESULTS")
    print("=" * 100)

    ok = [r for r in results if "error" not in r]
    clean = [r for r in ok if "Clean" in r["label"]]
    poisoned = [r for r in ok if "Poison" in r["label"]]

    if clean:
        avg_sg = sum(r["subgraph_size"] for r in clean) / len(clean)
        avg_scc = sum(r["scc_size"] for r in clean) / len(clean)
        avg_ratio = sum(r["ratio"] for r in clean) / len(clean)
        print(f"\nClean runs (n={len(clean)}):")
        print(f"  Avg SCC: {avg_scc:.1f}, Avg Subgraph: {avg_sg:.1f}, Avg Ratio: {avg_ratio:.1%}")

    if poisoned:
        avg_sg = sum(r["subgraph_size"] for r in poisoned) / len(poisoned)
        avg_scc = sum(r["scc_size"] for r in poisoned) / len(poisoned)
        avg_ratio = sum(r["ratio"] for r in poisoned) / len(poisoned)
        hits = sum(1 for r in poisoned if r.get("target_hit"))
        top5 = sum(1 for r in poisoned if 0 < r.get("target_rank", -1) <= 5)
        print(f"\nPoisoned runs (n={len(poisoned)}):")
        print(f"  Avg SCC: {avg_scc:.1f}, Avg Subgraph: {avg_sg:.1f}, Avg Ratio: {avg_ratio:.1%}")
        print(f"  Target in subgraph: {hits}/{len(poisoned)} = {hits/len(poisoned)*100:.0f}%")
        print(f"  Target in top-5: {top5}/{len(poisoned)} = {top5/len(poisoned)*100:.0f}%")

        print(f"\n  {'Label':<55} | SCC | SG | Ratio | Hit | Rank")
        print(f"  {'-'*90}")
        for r in poisoned:
            print(f"  {r['label']:<55} | {r['scc_size']:>3} | {r['subgraph_size']:>2} | {r['ratio']:>5.1%} | "
                  f"{'Y' if r.get('target_hit') else 'N':>3} | {r.get('target_rank', -1):>4}")

    print(f"\nFull results -> {out}")
    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
