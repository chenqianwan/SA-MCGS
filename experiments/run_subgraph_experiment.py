"""Risk Subgraph Extraction experiment.

Instead of ranking the perpetrator #1, we extract a Minimal Conflict
Subgraph from the MCGS search trace and check whether the perpetrator
is on the extracted risk path.

Compares:
  1. AlphaGo MCGS  — uses EdgeStats for reverse traceback
  2. Joint LLM     — uses dependency graph structure only (ablation)
  3. Random         — random subgraph of same size (baseline)
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.models.graph import DependencyGraph, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.modules.scc_sampler import SCCSampler

from experiments.perturbation import perturb_type_c

RESULTS_DIR = Path("experiments/results")


# ── Subgraph Extraction ─────────────────────────────────────────────

def extract_subgraph_from_mcgs(
    victims: set[str],
    edge_details: dict[str, dict],
    scc_ids: list[str],
    conflict_threshold: float = 0.3,
    max_hops: int = 3,
) -> dict:
    """Reverse-trace from victims through high-conflict edges."""
    reverse_adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for _key, info in edge_details.items():
        src, tgt = info["source"], info["target"]
        avg_c = info["avg_conflict"]
        if avg_c >= conflict_threshold:
            reverse_adj[tgt].append((src, avg_c))

    subgraph_nodes = set(victims)
    paths: list[list[str]] = []

    for victim in victims:
        queue: deque[tuple[str, list[str], float]] = deque()
        queue.append((victim, [victim], 1.0))
        visited = {victim}

        while queue:
            node, path, score = queue.popleft()
            if len(path) > max_hops + 1:
                continue

            for upstream, edge_conflict in reverse_adj.get(node, []):
                if upstream in visited:
                    continue
                visited.add(upstream)
                new_path = path + [upstream]
                new_score = score * edge_conflict
                subgraph_nodes.add(upstream)

                if upstream not in victims:
                    paths.append(list(reversed(new_path)))

                queue.append((upstream, new_path, new_score))

    ranked_paths = sorted(paths, key=lambda p: len(p))

    return {
        "nodes": sorted(subgraph_nodes),
        "size": len(subgraph_nodes),
        "paths": ranked_paths[:10],
    }


def extract_subgraph_from_graph(
    victims: set[str],
    scc_ids: list[str],
    internal_edges: list[tuple[str, str]],
    max_hops: int = 2,
) -> dict:
    """Simpler extraction using raw dependency graph (for Joint LLM ablation)."""
    reverse_adj: dict[str, list[str]] = defaultdict(list)
    for src, tgt in internal_edges:
        reverse_adj[tgt].append(src)

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
            for upstream in reverse_adj.get(node, []):
                if upstream in visited or upstream not in set(scc_ids):
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
        "paths": sorted(paths, key=lambda p: len(p))[:10],
    }


def random_subgraph(
    scc_ids: list[str],
    target_size: int,
    n_trials: int = 1000,
) -> float:
    """Monte Carlo estimate of random hit rate for a given subgraph size."""
    n = len(scc_ids)
    if target_size >= n:
        return 1.0
    hits = sum(1 for _ in range(n_trials) if random.sample(range(n), target_size))
    return target_size / n


def evaluate_subgraph(
    subgraph: dict,
    target_id: str,
    scc_size: int,
) -> dict:
    """Compute metrics for a subgraph extraction result."""
    nodes = set(subgraph["nodes"])
    hit = target_id in nodes
    size = subgraph["size"]

    target_on_path = False
    shortest_path_with_target = None
    for path in subgraph.get("paths", []):
        if target_id in path:
            target_on_path = True
            if shortest_path_with_target is None or len(path) < len(shortest_path_with_target):
                shortest_path_with_target = path

    random_hit_rate = size / scc_size

    return {
        "hit": hit,
        "target_on_path": target_on_path,
        "subgraph_size": size,
        "scc_size": scc_size,
        "coverage": size / scc_size,
        "precision": 1.0 / (size - len([n for n in nodes]) + 1) if hit else 0,
        "lift_vs_random": (1.0 / random_hit_rate) if hit else 0,
        "shortest_path": shortest_path_with_target,
    }


# ── AlphaGo MCGS runner ─────────────────────────────────────────────

async def run_alphago(llm_client, graph, config, scc_info):
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
        "virtual_loss_weight": 3,
        "temperature": 0.3,
        "max_tokens": 2048,
        "tt_max_reuse": 3,
        "dirichlet_alpha": 0.3,
        "dirichlet_weight": 0.25,
    }
    ag_config["detection"] = {"alpha": 0.1, "min_rollouts": 8}

    mcgs = AlphaGoMCGS(llm_client, ag_config)
    result = await mcgs.search(graph, scc_info)
    return result


# ── Joint LLM runner (ablation) ─────────────────────────────────────

async def run_joint_llm(llm_client, graph, config, scc_info, num_samples=12):
    """Run Joint LLM: K parallel calls on full SCC, aggregate scores."""
    sampler = SCCSampler(llm_client, config)
    sampler.num_samples = num_samples
    sampler.temperature = 0.7

    clauses = [graph.clauses[cid] for cid in scc_info.clause_ids if cid in graph.clauses]
    internal_edges = [
        e for e in graph.edges
        if e.source in set(scc_info.clause_ids) and e.target in set(scc_info.clause_ids)
    ]

    prompt = sampler._build_joint_prompt(clauses, internal_edges, [], compact=len(clauses) >= 6)

    tasks = [
        llm_client.call_json(prompt, temperature=0.7, max_tokens=4096)
        for _ in range(num_samples)
    ]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    score_matrix: dict[str, list[float]] = {cid: [] for cid in scc_info.clause_ids}

    for resp in responses:
        if isinstance(resp, Exception):
            continue
        evals = resp.get("clause_evaluations", resp.get("evaluations", resp))
        for cid in scc_info.clause_ids:
            if cid in evals:
                val = evals[cid]
                if isinstance(val, dict):
                    score = float(val.get("risk_score", val.get("overall_risk_score", 0.5)))
                elif isinstance(val, (int, float)):
                    score = float(val)
                else:
                    score = 0.5
                score_matrix[cid].append(score)
            else:
                score_matrix[cid].append(0.5)

    clause_details = {}
    for cid, scores in score_matrix.items():
        mean_s = sum(scores) / max(1, len(scores))
        clause_details[cid] = {
            "mean_score": mean_s,
            "scores": scores,
            "visit_count": len(scores),
        }

    avg_all = []
    for scores in score_matrix.values():
        avg_all.extend(scores)
    pool_mean = sum(avg_all) / max(1, len(avg_all))
    pool_std = (sum((s - pool_mean) ** 2 for s in avg_all) / max(1, len(avg_all))) ** 0.5

    oc_detected = set()
    if pool_std > 1e-6:
        pool_median = sorted(avg_all)[len(avg_all) // 2]
        for cid, scores in score_matrix.items():
            if len(scores) < 3:
                continue
            clause_mean = sum(scores) / len(scores)
            z = (clause_mean - pool_mean) / pool_std
            z_det = z > 1.5
            ranks = [sum(1 for s2 in avg_all if s2 <= s) / len(avg_all) for s in scores]
            rank_det = (sum(ranks) / len(ranks)) > 0.8
            exc = sum(1 for s in scores if s > pool_median) / len(scores)
            exc_det = exc > 0.8
            if sum([z_det, rank_det, exc_det]) >= 2:
                oc_detected.add(cid)

    ranked = sorted(clause_details.items(), key=lambda x: -x[1]["mean_score"])

    return {
        "method": "joint_llm",
        "oc_detected_clauses": sorted(oc_detected),
        "clause_details": clause_details,
        "ranking_by_risk": [(cid, info["mean_score"]) for cid, info in ranked],
        "num_samples": num_samples,
    }


# ── Main experiment ──────────────────────────────────────────────────

async def run_case(llm_client, graph, config, target_id, label):
    scc = next((s for s in graph.sccs if target_id in s.clause_ids), None)
    if not scc:
        logger.error(f"Cannot find SCC for {target_id}")
        return None

    n = len(scc.clause_ids)
    logger.info(f"\n{'='*70}")
    logger.info(f"CASE: {label} | target={target_id} | scc_size={n}")
    logger.info(f"{'='*70}")

    pg = perturb_type_c(graph, scc.clause_ids, target_id)
    DomainGraphPruner(config).prune(pg)
    pg = TarjanSCCDetector().detect(pg)
    pert_scc = next((s for s in pg.sccs if target_id in s.clause_ids), None)
    if not pert_scc:
        logger.error(f"Cannot find perturbed SCC for {target_id}")
        return None

    internal_edges_tuples = [
        (e.source, e.target) for e in pg.edges
        if e.source in set(pert_scc.clause_ids) and e.target in set(pert_scc.clause_ids)
    ]

    t0 = time.monotonic()

    logger.info("Running AlphaGo MCGS (clean + perturbed) ...")
    clean_ag, pert_ag = await asyncio.gather(
        run_alphago(llm_client, graph, config, scc),
        run_alphago(llm_client, pg, config, pert_scc),
    )

    logger.info("Running Joint LLM (clean + perturbed) ...")
    clean_jl, pert_jl = await asyncio.gather(
        run_joint_llm(llm_client, graph, config, scc),
        run_joint_llm(llm_client, pg, config, pert_scc),
    )

    elapsed = time.monotonic() - t0

    # ── Victim sets ──
    ag_clean_oc = set(clean_ag["oc_detected_clauses"])
    ag_pert_oc = set(pert_ag["oc_detected_clauses"])
    ag_victims = ag_pert_oc - ag_clean_oc

    jl_clean_oc = set(clean_jl["oc_detected_clauses"])
    jl_pert_oc = set(pert_jl["oc_detected_clauses"])
    jl_victims = jl_pert_oc - jl_clean_oc

    logger.info(f"  AG victims (new OC): {sorted(ag_victims)} ({len(ag_victims)})")
    logger.info(f"  JL victims (new OC): {sorted(jl_victims)} ({len(jl_victims)})")

    # ── Determine effective victim sets with fallbacks ──
    def pick_victims(victims, pert_oc, ranking, top_k=5):
        if victims:
            return victims, "delta_oc"
        if pert_oc:
            return pert_oc, "pert_oc"
        top_ids = {cid for cid, _ in ranking[:top_k]}
        return top_ids, "top_k_risk"

    ag_effective, ag_src = pick_victims(
        ag_victims, ag_pert_oc, pert_ag["ranking_by_risk"]
    )
    jl_effective, jl_src = pick_victims(
        jl_victims, jl_pert_oc, pert_jl["ranking_by_risk"]
    )
    logger.info(f"  AG effective victims ({ag_src}): {sorted(ag_effective)}")
    logger.info(f"  JL effective victims ({jl_src}): {sorted(jl_effective)}")

    # ── Subgraph extraction ──

    # Method 1: AlphaGo MCGS edge-guided
    ag_subgraph = extract_subgraph_from_mcgs(
        victims=ag_effective,
        edge_details=pert_ag.get("edge_details", {}),
        scc_ids=list(pert_scc.clause_ids),
        conflict_threshold=0.3,
        max_hops=3,
    )
    ag_eval = evaluate_subgraph(ag_subgraph, target_id, n)

    # Method 2: Joint LLM + graph structure
    jl_subgraph = extract_subgraph_from_graph(
        victims=jl_effective,
        scc_ids=list(pert_scc.clause_ids),
        internal_edges=internal_edges_tuples,
        max_hops=2,
    )
    jl_eval = evaluate_subgraph(jl_subgraph, target_id, n)

    # Method 3: Random baseline (same size as AG subgraph)
    random_hit = ag_subgraph["size"] / n

    # ── Method 4: Differential Edge Analysis (AG clean vs perturbed) ──
    clean_edges = clean_ag.get("edge_details", {})
    pert_edges = pert_ag.get("edge_details", {})

    edge_deltas = []
    for key, pert_info in pert_edges.items():
        clean_info = clean_edges.get(key, {"avg_conflict": 0, "visit_count": 0})
        delta = pert_info["avg_conflict"] - clean_info.get("avg_conflict", 0)
        if pert_info["visit_count"] >= 3:
            edge_deltas.append({
                "edge": key,
                "source": pert_info["source"],
                "target": pert_info["target"],
                "clean_conflict": clean_info.get("avg_conflict", 0),
                "pert_conflict": pert_info["avg_conflict"],
                "delta": delta,
            })

    edge_deltas.sort(key=lambda x: -x["delta"])
    top_delta_edges = edge_deltas[:15]

    delta_nodes = set()
    for ed in edge_deltas:
        if ed["delta"] > 0.1:
            delta_nodes.add(ed["source"])
            delta_nodes.add(ed["target"])

    delta_subgraph = {
        "nodes": sorted(delta_nodes),
        "size": len(delta_nodes),
        "top_edges": top_delta_edges[:10],
        "paths": [],
    }
    delta_eval = evaluate_subgraph(delta_subgraph, target_id, n)

    # ── Method 5: Differential Node Risk (clean vs perturbed risk scores) ──
    clean_details = clean_ag.get("clause_details", {})
    pert_details = pert_ag.get("clause_details", {})

    node_deltas = []
    for cid in pert_scc.clause_ids:
        clean_risk = clean_details.get(cid, {}).get("mean_score", 0)
        pert_risk = pert_details.get(cid, {}).get("mean_score", 0)
        delta = pert_risk - clean_risk
        node_deltas.append({
            "clause_id": cid,
            "clean_risk": clean_risk,
            "pert_risk": pert_risk,
            "delta": delta,
        })

    node_deltas.sort(key=lambda x: -abs(x["delta"]))

    top_delta_k = max(5, n // 3)
    delta_node_set = set()
    for nd in node_deltas[:top_delta_k]:
        if abs(nd["delta"]) > 0.02:
            delta_node_set.add(nd["clause_id"])

    node_delta_subgraph = {
        "nodes": sorted(delta_node_set),
        "size": len(delta_node_set),
        "paths": [],
    }
    node_delta_eval = evaluate_subgraph(node_delta_subgraph, target_id, n)

    # ── Print results ──
    logger.info(f"\n{'='*70}")
    logger.info(f"SUBGRAPH EXTRACTION RESULTS: {label}")
    logger.info(f"{'='*70}")

    logger.info(f"\n  [AlphaGo MCGS] Subgraph: {ag_subgraph['size']}/{n} nodes")
    logger.info(f"    Nodes: {ag_subgraph['nodes']}")
    logger.info(f"    Target HIT: {'YES' if ag_eval['hit'] else 'NO'}")
    logger.info(f"    Target on path: {'YES' if ag_eval['target_on_path'] else 'NO'}")
    logger.info(f"    Coverage: {ag_eval['coverage']:.1%}")
    if ag_eval['shortest_path']:
        logger.info(f"    Shortest path with target: {' → '.join(ag_eval['shortest_path'])}")
    logger.info(f"    Top paths:")
    for i, path in enumerate(ag_subgraph["paths"][:5]):
        marker = " ◀ HAS TARGET" if target_id in path else ""
        logger.info(f"      {i+1}. {' → '.join(path)}{marker}")

    logger.info(f"\n  [Joint LLM] Subgraph: {jl_subgraph['size']}/{n} nodes")
    logger.info(f"    Nodes: {jl_subgraph['nodes']}")
    logger.info(f"    Target HIT: {'YES' if jl_eval['hit'] else 'NO'}")
    logger.info(f"    Target on path: {'YES' if jl_eval['target_on_path'] else 'NO'}")
    logger.info(f"    Coverage: {jl_eval['coverage']:.1%}")

    logger.info(f"\n  [Diff-Edge] Subgraph: {delta_subgraph['size']}/{n} nodes")
    logger.info(f"    Nodes: {delta_subgraph['nodes']}")
    logger.info(f"    Target HIT: {'YES' if delta_eval['hit'] else 'NO'}")
    logger.info(f"    Coverage: {delta_eval['coverage']:.1%}")
    logger.info(f"    Top Δ edges:")
    for ed in top_delta_edges[:8]:
        marker = " ◀" if target_id in (ed["source"], ed["target"]) else ""
        logger.info(
            f"      {ed['source']}->{ed['target']}: "
            f"clean={ed['clean_conflict']:.2f} pert={ed['pert_conflict']:.2f} "
            f"Δ={ed['delta']:+.2f}{marker}"
        )

    logger.info(f"\n  [Diff-Node] Subgraph: {node_delta_subgraph['size']}/{n} nodes")
    logger.info(f"    Nodes: {node_delta_subgraph['nodes']}")
    logger.info(f"    Target HIT: {'YES' if node_delta_eval['hit'] else 'NO'}")
    logger.info(f"    Coverage: {node_delta_eval['coverage']:.1%}")
    logger.info(f"    Top Δ nodes:")
    for nd in node_deltas[:8]:
        marker = " ◀ TARGET" if nd["clause_id"] == target_id else ""
        logger.info(
            f"      {nd['clause_id']:<12}: "
            f"clean={nd['clean_risk']:.3f} pert={nd['pert_risk']:.3f} "
            f"Δ={nd['delta']:+.3f}{marker}"
        )

    logger.info(f"\n  [Random] Same size ({ag_subgraph['size']}/{n})")
    logger.info(f"    Expected hit rate: {random_hit:.1%}")

    logger.info(f"\n  Lift vs random: AG={ag_eval['lift_vs_random']:.1f}x")
    logger.info(f"  Total time: {elapsed:.0f}s")

    return {
        "label": label,
        "target_id": target_id,
        "scc_size": n,
        "time": elapsed,
        "alphago": {
            "clean_oc": sorted(ag_clean_oc),
            "pert_oc": sorted(ag_pert_oc),
            "victims": sorted(ag_victims),
            "effective_victims": sorted(ag_effective),
            "victim_source": ag_src,
            "subgraph": ag_subgraph,
            "eval": ag_eval,
            "llm_calls": pert_ag.get("llm_calls", 0),
            "risk_ranking": pert_ag["ranking_by_risk"],
        },
        "joint_llm": {
            "clean_oc": sorted(jl_clean_oc),
            "pert_oc": sorted(jl_pert_oc),
            "victims": sorted(jl_victims),
            "effective_victims": sorted(jl_effective),
            "victim_source": jl_src,
            "subgraph": jl_subgraph,
            "eval": jl_eval,
        },
        "diff_edge": {
            "subgraph": delta_subgraph,
            "eval": delta_eval,
            "top_edges": top_delta_edges[:10],
        },
        "diff_node": {
            "subgraph": node_delta_subgraph,
            "eval": node_delta_eval,
            "top_nodes": node_deltas[:10],
        },
        "random_hit_rate": random_hit,
    }


async def main():
    logger.info("=" * 70)
    logger.info("RISK SUBGRAPH EXTRACTION EXPERIMENT")
    logger.info("  From culprit-hunting to conflict-path explanation")
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

    results = []

    r = await run_case(llm_client, graph, config, "bgb_240a", "5n_bgb_240a")
    if r:
        results.append(r)

    r = await run_case(llm_client, graph, config, "bgb_327o", "24n_bgb_327o")
    if r:
        results.append(r)

    # ── Summary table ──
    print("\n" + "=" * 100)
    print("RISK SUBGRAPH EXTRACTION — FINAL SUMMARY")
    print("=" * 100)
    print(f"{'Case':<18} | {'Method':<12} | {'Victims':>7} | "
          f"{'Subgraph':>8} | {'Cover%':>6} | {'HIT':>3} | "
          f"{'OnPath':>6} | {'Lift':>5}")
    print("-" * 100)

    for r in results:
        methods = [
            ("AG-MCGS", "alphago"),
            ("Joint-LLM", "joint_llm"),
            ("Diff-Edge", "diff_edge"),
            ("Diff-Node", "diff_node"),
        ]
        for method_name, method_key in methods:
            m = r[method_key]
            e = m["eval"]
            victims_str = str(len(m.get("victims", []))) if "victims" in m else "—"
            print(
                f"{r['label']:<18} | {method_name:<12} | "
                f"{victims_str:>7} | "
                f"{m['subgraph']['size']:>3}/{r['scc_size']:<3} | "
                f"{e['coverage']:>5.0%} | "
                f"{'YES' if e['hit'] else ' NO':>3} | "
                f"{'YES' if e['target_on_path'] else ' NO':>6} | "
                f"{e['lift_vs_random']:>4.1f}x"
            )
        print(
            f"{r['label']:<18} | {'Random':<12} | "
            f"{'—':>7} | "
            f"{r['alphago']['subgraph']['size']:>3}/{r['scc_size']:<3} | "
            f"{r['random_hit_rate']:>5.0%} | "
            f"{'—':>3} | {'—':>6} | 1.0x"
        )
        print("-" * 100)

    out_path = RESULTS_DIR / "subgraph_experiment.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to {out_path}")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
