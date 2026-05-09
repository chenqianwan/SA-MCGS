"""Ultimate experiment: CLAUSE real perturbations on cross-contract deal package SCCs.

Injects CLAUSE benchmark perturbations (5 difficulty tiers) into merged deal-package
graphs, runs SA-MCGS, and measures detection + localization across difficulty levels.

Difficulty tiers:
  T1 (easy):   inconsistencies_inText   — direct numerical/factual contradictions
  T2 (medium): structural_flaws_inText  — broken cross-references, hierarchy issues
  T3 (medium): misalignedTerminology_inText — inconsistent use of defined terms
  T4 (hard):   omission_inText          — removed critical information
  T5 (hard):   ambiguity_inText         — vague/contradictory language introduced
"""
from __future__ import annotations

import asyncio
import json
import os
import re
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

NUM_REPEATS = 2
CONCURRENCY = 8

CLAUSE_BASE = Path("data/clause_benchmark_repo/datasets/CUAD_Dataset")

DIFFICULTY_TIERS = {
    "T1_inconsistencies":  ("inconsistencies_inText",       "easy"),
    "T2_structural_flaws": ("structural_flaws_inText",      "medium"),
    "T3_misaligned_term":  ("misalignedTerminology_inText", "medium"),
    "T4_omission":         ("omission_inText",              "hard"),
    "T5_ambiguity":        ("ambiguity_inText",             "hard"),
}

DEAL_CONTRACT_FILES = {
    "Reynolds (Supply+Service)": {
        "C0": "perturbed_ReynoldsConsumerProductsInc_20191115_S-1_EX-10.18_11896469_EX-10.18_Supply Agreement.txt.json",
        "C1": "perturbed_ReynoldsConsumerProductsInc_20200121_S-1A_EX-10.22_11948918_EX-10.22_Service Agreement.txt.json",
    },
    "AzulSa (2xMaintenance)": {
        "C0": "perturbed_AzulSa_20170303_F-1A_EX-10.3_9943903_EX-10.3_Maintenance Agreement1.txt.json",
        "C1": "perturbed_AzulSa_20170303_F-1A_EX-10.3_9943903_EX-10.3_Maintenance Agreement2.txt.json",
    },
    "NETGEAR (Distributor+2Amend)": {
        "C0": "perturbed_NETGEAR,INC_04_21_2003-EX-10.16-DISTRIBUTOR AGREEMENT.txt.json",
        "C1": "perturbed_NETGEAR,INC_04_21_2003-EX-10.16-AMENDMENT TO THE DISTRIBUTOR AGREEMENT BETWEEN INGRAM MICRO AND NETGEAR.txt.json",
        "C2": "perturbed_NETGEAR,INC_04_21_2003-EX-10.16- AMENDMENT #2 TO THE DISTRIBUTION AGREEMENT.txt.json",
    },
}


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


def parse_section_id(location: str) -> str:
    """Extract a numeric section ID from CLAUSE location strings like 'Section 5.4', '3', '6.1'."""
    loc = location.strip()
    loc = re.sub(r'^(Section|SECTION|Article|ARTICLE|ARTICLE\s+[IVX]+)\s*', '', loc)
    loc = re.sub(r'\s*(Definitions|Fees|Policies).*$', '', loc, flags=re.IGNORECASE)
    loc = re.sub(r'[.,:;)\s]+$', '', loc)
    m = re.match(r'^(\d+(?:\.\d+)*(?:\([a-z]\))?)', loc)
    if m:
        return m.group(1)
    m = re.match(r'^(\d+)', loc)
    if m:
        return m.group(1)
    return loc


def find_target_in_merged(graph: DependencyGraph, section_id: str, contract_prefix: str) -> str | None:
    """Map a CLAUSE section number to a node in the merged graph (with C0_, C1_ prefix)."""
    candidate = f"{contract_prefix}_{section_id}"
    if candidate in graph.clauses:
        return candidate

    parts = section_id.split(".")
    for i in range(len(parts), 0, -1):
        c = f"{contract_prefix}_{'.'.join(parts[:i])}"
        if c in graph.clauses:
            return c

    sec_id_clean = section_id.replace("(", "").replace(")", "")
    for cid in graph.clauses:
        if cid.startswith(contract_prefix + "_") and sec_id_clean in cid:
            return cid
    return None


def load_clause_perturbations(pkg_name: str, tier_name: str, cat_dir_name: str) -> list[dict]:
    """Load all CLAUSE perturbations for a deal package and category."""
    contract_files = DEAL_CONTRACT_FILES.get(pkg_name, {})
    all_perts = []

    for prefix, pert_file in contract_files.items():
        path = CLAUSE_BASE / cat_dir_name / pert_file
        if not path.exists():
            continue
        data = json.load(open(path, encoding="utf-8"))
        perts = []
        for item in (data if isinstance(data, list) else [data]):
            perts.extend(item.get("perturbation", []))
        for p in perts:
            p["_contract_prefix"] = prefix
            p["_tier"] = tier_name
            p["_pkg"] = pkg_name
        all_perts.extend(perts)
    return all_perts


def inject_perturbation(
    graph: DependencyGraph, pert: dict, scc_nodes: set[str],
) -> tuple[DependencyGraph, str | None, str | None, bool]:
    """Inject a CLAUSE perturbation into the merged graph.
    Returns (perturbed_graph, target_id, contra_id, target_in_scc).
    """
    g = graph.model_copy(deep=True)
    prefix = pert["_contract_prefix"]

    loc = pert.get("location", "")
    contra_loc = pert.get("contradicted_location", "")
    changed_text = pert.get("changed_text", "")

    sec_id = parse_section_id(loc)
    target_id = find_target_in_merged(g, sec_id, prefix)

    contra_sec = parse_section_id(contra_loc) if contra_loc else ""
    contra_id = find_target_in_merged(g, contra_sec, prefix) if contra_sec else None

    if target_id and changed_text:
        clause = g.clauses[target_id]
        clause.metadata["_original_content"] = clause.content
        clause.content = changed_text[:3000]
        clause.metadata["_perturbed"] = "clause_real"

    target_in_scc = target_id in scc_nodes if target_id else False

    return g, target_id, contra_id, target_in_scc


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


async def run_one(llm_client, graph, config, scc, label, target_id, contra_id,
                  target_in_scc, tier, difficulty, sem):
    async with sem:
        print(f"[START] {label}")
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
            contra_hit = contra_id in sg_nodes if contra_id else False
            target_in_oc = target_id in oc if target_id else False
            contra_in_oc = contra_id in oc if contra_id else False

            ranked_ids = [cid for cid, _ in ranking]
            target_rank = ranked_ids.index(target_id) + 1 if target_id and target_id in ranked_ids else -1
            contra_rank = ranked_ids.index(contra_id) + 1 if contra_id and contra_id in ranked_ids else -1

            detected = target_hit or contra_hit or target_in_oc or contra_in_oc
            detected = detected or (0 < target_rank <= 5) or (0 < contra_rank <= 5)

            ratio = sg_size / scc.size if scc.size > 0 else 1.0
            status = "HIT" if detected else "MISS"
            print(f"[DONE] {label} ({elapsed:.0f}s) — SCC={scc.size}→SG={sg_size} "
                  f"({ratio:.0%}), {status}, tgt_rank={target_rank}, in_scc={target_in_scc}")

            return {
                "label": label, "tier": tier, "difficulty": difficulty,
                "scc_size": scc.size, "subgraph_size": sg_size,
                "ratio": round(ratio, 3),
                "target_id": target_id, "contra_id": contra_id,
                "target_in_scc": target_in_scc,
                "target_hit": target_hit, "contra_hit": contra_hit,
                "target_in_oc": target_in_oc, "contra_in_oc": contra_in_oc,
                "target_rank": target_rank, "contra_rank": contra_rank,
                "detected": detected,
                "oc_count": len(oc),
                "top5": [(c, round(s, 4)) for c, s in ranking[:5]],
                "subgraph_nodes": sg_nodes,
                "time": round(elapsed, 1),
            }
        except Exception as e:
            print(f"[FAIL] {label}: {e}")
            import traceback; traceback.print_exc()
            return {"label": label, "tier": tier, "difficulty": difficulty,
                    "target_in_scc": target_in_scc, "error": str(e)}


async def run_clean(llm_client, graph, config, scc, label, sem):
    async with sem:
        print(f"[START] {label}")
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
            ratio = sg_size / scc.size if scc.size > 0 else 1.0
            print(f"[DONE] {label} ({elapsed:.0f}s) — SCC={scc.size}→SG={sg_size} ({ratio:.0%}), Clean")
            return {
                "label": label, "tier": "clean", "difficulty": "clean",
                "scc_size": scc.size, "subgraph_size": sg_size,
                "ratio": round(ratio, 3), "oc_count": len(oc),
                "detected": False, "target_in_scc": False,
                "top5": [(c, round(s, 4)) for c, s in ranking[:5]],
                "subgraph_nodes": sg_nodes, "time": round(elapsed, 1),
            }
        except Exception as e:
            print(f"[FAIL] {label}: {e}")
            return {"label": label, "tier": "clean", "difficulty": "clean", "error": str(e)}


async def main():
    os.environ["XHUB_API_KEY"] = os.environ.get("XHUB_API_KEY", "")
    config = {
        "llm": {
            "provider": "openai", "model": "deepseek-chat",
            "base_url": "https://api3.xhub.chat/v1",
            "api_key_env": "XHUB_API_KEY",
            "max_concurrent_calls": 12, "timeout": 120,
        }
    }
    if not os.environ.get("XHUB_API_KEY"):
        api_key = input("Enter xhub API key: ").strip()
        os.environ["XHUB_API_KEY"] = api_key

    llm_client = OpenAIClient(config["llm"])
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = []

    for pkg_name in DEAL_CONTRACT_FILES:
        print(f"\n{'='*80}")
        print(f"Loading {pkg_name}...")
        graph = load_and_merge(pkg_name)
        if not graph or not graph.sccs:
            print(f"  No SCCs, skip")
            continue

        best_scc = max(graph.sccs, key=lambda s: s.size)
        scc_nodes = set(best_scc.clause_ids)
        print(f"  Nodes: {len(graph.clauses)}, Best SCC: {best_scc.size}, members: {sorted(scc_nodes)[:8]}...")

        for r in range(1, NUM_REPEATS + 1):
            tasks.append(run_clean(
                llm_client, graph, config, best_scc,
                f"{pkg_name}|Clean|R{r}", sem,
            ))

        for tier_name, (cat_dir, difficulty) in DIFFICULTY_TIERS.items():
            perts = load_clause_perturbations(pkg_name, tier_name, cat_dir)
            if not perts:
                continue

            for pidx, pert in enumerate(perts):
                perturbed_graph, target_id, contra_id, in_scc = inject_perturbation(
                    graph, pert, scc_nodes,
                )
                prefix = pert["_contract_prefix"]
                loc = pert.get("location", "?")[:15]

                for r in range(1, NUM_REPEATS + 1):
                    label = (f"{pkg_name}|{tier_name}|{prefix}_{loc}|P{pidx}R{r}")
                    tasks.append(run_one(
                        llm_client, perturbed_graph, config, best_scc,
                        label, target_id, contra_id, in_scc,
                        tier_name, difficulty, sem,
                    ))

    total = len(tasks)
    print(f"\n{'='*80}")
    print(f"Total experiments: {total}")
    print(f"Concurrency: {CONCURRENCY}")
    print("Launching...\n")

    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r]

    out = Path("experiments/results/deal_clause_ultimate.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))

    # ── Summary ──
    print("\n" + "=" * 120)
    print("ULTIMATE EXPERIMENT: CLAUSE Real Perturbations × Cross-Contract Deal Packages")
    print("=" * 120)

    ok = [r for r in results if "error" not in r]
    errs = [r for r in results if "error" in r]
    clean = [r for r in ok if r["tier"] == "clean"]
    poisoned = [r for r in ok if r["tier"] != "clean"]

    if clean:
        avg_ratio = sum(r["ratio"] for r in clean) / len(clean)
        avg_oc = sum(r["oc_count"] for r in clean) / len(clean)
        print(f"\nClean baseline (n={len(clean)}): avg_ratio={avg_ratio:.1%}, avg_OC={avg_oc:.1f}")

    in_scc = [r for r in poisoned if r.get("target_in_scc")]
    not_in_scc = [r for r in poisoned if not r.get("target_in_scc")]

    print(f"\nPoisoned runs total: {len(poisoned)}")
    print(f"  Target in SCC: {len(in_scc)}")
    print(f"  Target NOT in SCC: {len(not_in_scc)}")

    if in_scc:
        det = sum(1 for r in in_scc if r.get("detected"))
        avg_ratio = sum(r["ratio"] for r in in_scc) / len(in_scc)
        avg_rank = [r["target_rank"] for r in in_scc if r.get("target_rank", -1) > 0]
        print(f"\n  === IN-SCC Detection ===")
        print(f"  Detection rate: {det}/{len(in_scc)} = {det/len(in_scc)*100:.1f}%")
        print(f"  Avg subgraph ratio: {avg_ratio:.1%}")
        if avg_rank:
            print(f"  Avg target rank: {sum(avg_rank)/len(avg_rank):.1f}")

    # Per-difficulty breakdown
    print(f"\n{'='*120}")
    print(f"  {'Difficulty':<12} {'Tier':<25} {'In SCC':>6} | {'Detected':>10} {'Rate':>6} | "
          f"{'Avg Ratio':>10} | {'Avg Rank':>9} | {'Not-SCC':>7}")
    print(f"  {'-'*110}")

    for tier_name, (_, difficulty) in DIFFICULTY_TIERS.items():
        tier_runs = [r for r in poisoned if r.get("tier") == tier_name]
        tier_in_scc = [r for r in tier_runs if r.get("target_in_scc")]
        tier_not_scc = [r for r in tier_runs if not r.get("target_in_scc")]

        det_in = sum(1 for r in tier_in_scc if r.get("detected"))
        n_in = len(tier_in_scc)
        rate_str = f"{det_in}/{n_in} {det_in/n_in*100:.0f}%" if n_in else "N/A"
        ratio_str = f"{sum(r['ratio'] for r in tier_in_scc)/n_in:.0%}" if n_in else "N/A"
        ranks = [r["target_rank"] for r in tier_in_scc if r.get("target_rank", -1) > 0]
        rank_str = f"{sum(ranks)/len(ranks):.1f}" if ranks else "N/A"

        print(f"  {difficulty:<12} {tier_name:<25} {n_in:>6} | {rate_str:>10} {'':>6} | "
              f"{ratio_str:>10} | {rank_str:>9} | {len(tier_not_scc):>7}")

    # Per-deal-package breakdown
    print(f"\n{'='*120}")
    print("  Per-package breakdown (in-SCC only):")
    for pkg in DEAL_CONTRACT_FILES:
        pkg_runs = [r for r in in_scc if pkg in r.get("label", "")]
        if not pkg_runs:
            continue
        det = sum(1 for r in pkg_runs if r.get("detected"))
        avg_r = sum(r["ratio"] for r in pkg_runs) / len(pkg_runs)
        print(f"  {pkg:<35}: {det}/{len(pkg_runs)} detected, avg_ratio={avg_r:.0%}")

    if errs:
        print(f"\n--- ERRORS ({len(errs)}) ---")
        for r in errs[:5]:
            print(f"  {r.get('label', '?')}: {r.get('error', '?')}")

    print(f"\nFull results -> {out}")
    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
