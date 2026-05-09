"""CLAUSE Battle: SA-MCGS vs LLM Baselines on CUAD perturbed contracts.

Replicates the BGB experiment flow (run_pruning_v2.py) on CUAD data:
  load fullgraph → inject CLAUSE perturbation → AlphaGoMCGS.search → detection metrics

Target: 5 contracts × 2-3 perturbation categories × 3 repeats ≈ 45 runs.
API: DeepSeek-Chat via xhub.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.cuad_loader import CUADLoader
from src.models.graph import DependencyGraph, Edge, DependencyType, SCCInfo
from src.models.clause import Clause, ClauseType
from src.modules.tarjan import TarjanSCCDetector
from src.modules.alphago_mcgs import AlphaGoMCGS

# ── Paths ──
FULLGRAPH_DIR = Path("data/cuad/grpo_lex_replicated/fullgraphs")
CLAUSE_BASE = Path("data/clause_benchmark_repo/datasets/CUAD_Dataset")
ORIG_TXT_DIR = CLAUSE_BASE / "full_contract_txt"
RESULTS_DIR = Path("experiments/results")

NUM_REPEATS = 3
CONCURRENCY = 4

# ── 5 target contracts: best SCC × CLAUSE coverage ──
TARGET_CONTRACTS = [
    "PhasebioPharmaceuticalsInc_20200330_10-K_EX-10.21_12086810_EX-10.21_Development_Agreement",
    "VerizonAbsLlc_20200123_8-K_EX-10.4_11952335_EX-10.4_Service_Agreement",
    "HarpoonTherapeuticsInc_20200312_10-K_EX-10.18_12051356_EX-10.18_Development_Agreement",
    "ChinaRealEstateInformationCorp_20090929_F-1_EX-10.32_4771615_EX-10.32_Content_License_Agreement",
    "CytodynInc_20200109_10-Q_EX-10.5_11941634_EX-10.5_License_Agreement",
]

PERTURBATION_CATEGORIES = [
    "structural_flaws_inText",
    "omission_inText",
    "inconsistencies_inText",
]

# ── CLAUSE baselines from EACL 2026 paper (CUAD subset) ──
CLAUSE_BASELINES = {
    "GPT-4o-mini":  {"structural_flaws": 0.467, "omission": 0.450, "inconsistencies": 0.436},
    "Gemini-2.0":   {"structural_flaws": 0.558, "omission": 0.585, "inconsistencies": 0.628},
    "Gemini-2.5":   {"structural_flaws": 0.467, "omission": 0.637, "inconsistencies": 0.638},
    "LLaMA-3.3":    {"structural_flaws": 0.147, "omission": 0.503, "inconsistencies": 0.547},
}


# =====================================================================
# Graph loading & clause text enrichment
# =====================================================================

def load_contract_graph(contract_name: str) -> DependencyGraph:
    """Load pre-built fullgraph and convert to DependencyGraph with full clause text."""
    graph_path = FULLGRAPH_DIR / f"{contract_name}_fullgraph.json"
    loader = CUADLoader(str(FULLGRAPH_DIR.parent), config={"cuad": {"clause_only": False}})
    result = loader.load_single_graph(graph_path)
    if not result:
        raise FileNotFoundError(f"Cannot load graph: {graph_path}")
    _, graph = result

    orig_txt = _find_original_text(contract_name)
    if orig_txt:
        _enrich_clause_content(graph, orig_txt)

    return graph


def _find_original_text(contract_name: str) -> str | None:
    """Find the original contract text from CLAUSE full_contract_txt."""
    search_name = contract_name.replace("_", " ").replace(",", "").lower()
    for f in ORIG_TXT_DIR.iterdir():
        if f.suffix == ".txt":
            fname_norm = f.stem.replace("_", " ").replace(",", "").lower()
            if fname_norm == search_name or search_name in fname_norm or fname_norm in search_name:
                return f.read_text(encoding="utf-8", errors="replace")
    return None


def _enrich_clause_content(graph: DependencyGraph, full_text: str):
    """Map full contract text sections back to clause nodes for LLM evaluation."""
    sections = _split_into_sections(full_text)
    for clause_id, clause in graph.clauses.items():
        if clause.content and len(clause.content) > 50:
            continue
        if clause_id in sections:
            clause.content = sections[clause_id][:3000]
        elif clause.title and len(clause.title) > 10:
            clause.content = clause.title


def _split_into_sections(text: str) -> dict[str, str]:
    """Split contract text into sections by section number."""
    pattern = re.compile(
        r"^[\s]*(?:Section|SECTION|Article|ARTICLE)?\s*(\d+(?:\.\d+)*)\s*[.:\-–—)]\s*",
        re.MULTILINE,
    )
    sections: dict[str, str] = {}
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        sec_id = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else min(start + 5000, len(text))
        sections[sec_id] = text[start:end].strip()
    return sections


# =====================================================================
# Medium Implicit edge enhancement (same as analyze_implicit_refs.py)
# =====================================================================

def add_medium_implicit_edges(graph: DependencyGraph) -> DependencyGraph:
    """Add implicit edges to replicate the Medium Implicit mode from our SCC analysis."""
    node_map = {c.id: c for c in graph.clauses.values()}
    clause_ids = set(graph.clauses.keys())

    defines: dict[str, str] = {}
    uses: dict[str, list[str]] = {}

    for e in graph.edges:
        src_meta = graph.clauses.get(e.source, None)
        if not src_meta:
            continue
        if e.reasoning == "DEFINES" or e.dependency_type == DependencyType.DEFINES:
            if e.target.startswith("term:"):
                defines[e.target] = e.source
        if e.reasoning == "USES":
            if e.target.startswith("term:"):
                uses.setdefault(e.target, []).append(e.source)

    new_edges = []
    existing = {(e.source, e.target) for e in graph.edges}

    for term, definer in defines.items():
        if definer not in clause_ids:
            continue
        for user in uses.get(term, []):
            if user != definer and user in clause_ids and (user, definer) not in existing:
                new_edges.append(Edge(
                    source=user, target=definer,
                    dependency_type=DependencyType.REFERENCES,
                    weight=0.7, reasoning="STRONG_IMPLICIT",
                ))
                existing.add((user, definer))

    stopwords = {"party", "parties", "agreement", "company", "date", "section", "term", "terms", "notice"}
    term_users: dict[str, set[str]] = {}
    for e in graph.edges:
        if e.reasoning == "USES" and e.target.startswith("term:") and e.source in clause_ids:
            term_users.setdefault(e.target, set()).add(e.source)

    for term, user_set in term_users.items():
        tw = term.replace("term:", "").lower()
        if tw in stopwords:
            continue
        user_list = list(user_set)
        if not (2 <= len(user_list) <= 7):
            continue
        definer = defines.get(term)
        if len(user_list) == 2:
            a, b = user_list
            if definer and definer in user_list:
                other = a if b == definer else b
                if (other, definer) not in existing:
                    new_edges.append(Edge(source=other, target=definer,
                                         dependency_type=DependencyType.REFERENCES,
                                         weight=0.5, reasoning="MEDIUM_IMPLICIT"))
                    existing.add((other, definer))
            else:
                for pair in [(a, b), (b, a)]:
                    if pair not in existing:
                        new_edges.append(Edge(source=pair[0], target=pair[1],
                                              dependency_type=DependencyType.REFERENCES,
                                              weight=0.4, reasoning="MEDIUM_IMPLICIT"))
                        existing.add(pair)
        else:
            for u in user_list:
                if definer and u != definer and (u, definer) not in existing:
                    new_edges.append(Edge(source=u, target=definer,
                                         dependency_type=DependencyType.REFERENCES,
                                         weight=0.5, reasoning="MEDIUM_IMPLICIT"))
                    existing.add((u, definer))

    graph.edges.extend(new_edges)
    return graph


# =====================================================================
# CLAUSE perturbation injection
# =====================================================================

def find_clause_perturbations(contract_name: str, category: str) -> list[dict]:
    """Find CLAUSE perturbation JSON for a given contract and category."""
    cat_dir = CLAUSE_BASE / category
    if not cat_dir.is_dir():
        return []

    search_name = contract_name.replace("_", " ").replace(",", "").lower()
    for f in cat_dir.iterdir():
        if not f.suffix == ".json":
            continue
        fname_norm = f.stem.replace("perturbed_", "").replace(".txt", "")
        fname_norm = fname_norm.replace("_", " ").replace(",", "").lower()
        if search_name in fname_norm or fname_norm in search_name:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            perts = []
            if isinstance(data, list):
                for item in data:
                    perts.extend(item.get("perturbation", []))
            else:
                perts = data.get("perturbation", [])
            return perts
    return []


def find_target_node(graph: DependencyGraph, section_id: str) -> str | None:
    """Map a CLAUSE section number to the closest existing graph node."""
    if section_id in graph.clauses:
        return section_id

    parts = section_id.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in graph.clauses:
            return candidate
    return None


def inject_clause_perturbation(
    graph: DependencyGraph,
    perturbation: dict,
) -> tuple[DependencyGraph, str | None, str | None]:
    """Inject a CLAUSE perturbation into the graph (Type-A style text replacement).

    Returns (perturbed_graph, target_node_id, contra_node_id).
    """
    g = graph.model_copy(deep=True)

    loc = perturbation.get("location", "")
    contra_loc = perturbation.get("contradicted_location", "")
    changed_text = perturbation.get("changed_text", "")

    target_id = find_target_node(g, loc)
    contra_id = find_target_node(g, contra_loc)

    if target_id and changed_text:
        clause = g.clauses[target_id]
        clause.metadata["_original_content"] = clause.content
        clause.content = changed_text[:3000]
        clause.metadata["_perturbed"] = "clause_injection"
        clause.metadata["_clause_type"] = perturbation.get("type", "")
        clause.metadata["_location"] = loc
        clause.metadata["_contradicted_location"] = contra_loc

    return g, target_id, contra_id


# =====================================================================
# AlphaGoMCGS search (reused from run_pruning_v2.py)
# =====================================================================

def pick_victims(oc_detected: list[str], ranking: list, top_k: int = 5) -> set[str]:
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
    budget = min(300, max(40, n * 12))
    window_size = min(5, max(3, n // 6))
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


# =====================================================================
# Single experiment run
# =====================================================================

async def run_one(
    llm_client, graph: DependencyGraph, config: dict,
    contract_name: str, category: str, pert_idx: int,
    perturbation: dict, repeat_idx: int, sem: asyncio.Semaphore,
):
    label = f"{contract_name[:30]}|{category}|P{pert_idx}|R{repeat_idx}"
    async with sem:
        logger.info(f"[START] {label}")
        t0 = time.monotonic()
        try:
            perturbed_graph, target_id, contra_id = inject_clause_perturbation(graph, perturbation)

            perturbed_graph = add_medium_implicit_edges(perturbed_graph)
            perturbed_graph = TarjanSCCDetector().detect(perturbed_graph)

            all_scc_nodes = set()
            for scc in perturbed_graph.sccs:
                all_scc_nodes.update(scc.clause_ids)

            best_scc = None
            if contra_id:
                for scc in perturbed_graph.sccs:
                    if contra_id in scc.clause_ids:
                        best_scc = scc
                        break
            if not best_scc and target_id:
                for scc in perturbed_graph.sccs:
                    if target_id in scc.clause_ids:
                        best_scc = scc
                        break
            if not best_scc and perturbed_graph.sccs:
                best_scc = max(perturbed_graph.sccs, key=lambda s: s.size)

            if not best_scc or best_scc.size < 2:
                logger.warning(f"[SKIP] {label}: no viable SCC (size < 2)")
                return {"label": label, "contract": contract_name,
                        "category": category, "pert_idx": pert_idx,
                        "repeat": repeat_idx, "error": "no_scc"}

            scc_set = set(best_scc.clause_ids)
            n_nodes = len(best_scc.clause_ids)

            result = await run_mcgs(llm_client, perturbed_graph, config, best_scc)
            elapsed = time.monotonic() - t0

            oc = set(result.get("oc_detected_clauses", []))
            ranking = result.get("ranking_by_risk", [])
            victims = pick_victims(list(oc), ranking)
            sg_nodes, sg_size = extract_subgraph(
                victims, result.get("edge_details", {}),
                list(best_scc.clause_ids),
            )

            target_hit = target_id in sg_nodes if target_id else False
            contra_hit = contra_id in sg_nodes if contra_id else False
            target_in_oc = target_id in oc if target_id else False
            contra_in_oc = contra_id in oc if contra_id else False

            ranked_ids = [cid for cid, _ in ranking]
            target_rank = ranked_ids.index(target_id) + 1 if target_id and target_id in ranked_ids else -1
            contra_rank = ranked_ids.index(contra_id) + 1 if contra_id and contra_id in ranked_ids else -1
            target_in_top5 = 0 < target_rank <= 5
            contra_in_top5 = 0 < contra_rank <= 5

            detected = target_hit or contra_hit or target_in_oc or contra_in_oc or target_in_top5 or contra_in_top5

            logger.info(f"[DONE] {label} ({elapsed:.0f}s) — "
                        f"SCC={n_nodes}, OC={len(oc)}, SG={sg_size}, "
                        f"target_hit={target_hit}, contra_hit={contra_hit}, detected={detected}")

            return {
                "label": label, "contract": contract_name,
                "category": category, "pert_idx": pert_idx,
                "repeat": repeat_idx,
                "perturbation_type": perturbation.get("type", ""),
                "location": perturbation.get("location", ""),
                "contradicted_location": perturbation.get("contradicted_location", ""),
                "target_node": target_id, "contra_node": contra_id,
                "scc_id": best_scc.id, "scc_nodes": n_nodes,
                "oc_count": len(oc), "oc_detected": sorted(oc),
                "subgraph_size": sg_size, "subgraph_nodes": sg_nodes,
                "target_hit": target_hit, "contra_hit": contra_hit,
                "target_in_oc": target_in_oc, "contra_in_oc": contra_in_oc,
                "target_rank": target_rank, "contra_rank": contra_rank,
                "target_in_top5": target_in_top5, "contra_in_top5": contra_in_top5,
                "detected": detected,
                "avg_risk": round(
                    sum(s for _, s in ranking) / max(n_nodes, 1), 4),
                "top5_risk": [(c, round(s, 4)) for c, s in ranking[:5]],
                "llm_calls": result.get("llm_calls", 0),
                "time": round(elapsed, 1),
            }
        except Exception as e:
            logger.error(f"[FAIL] {label}: {e}")
            import traceback
            traceback.print_exc()
            return {"label": label, "contract": contract_name,
                    "category": category, "pert_idx": pert_idx,
                    "repeat": repeat_idx, "error": str(e)}


# =====================================================================
# Clean baseline run (no perturbation)
# =====================================================================

async def run_clean(
    llm_client, graph: DependencyGraph, config: dict,
    contract_name: str, repeat_idx: int, sem: asyncio.Semaphore,
):
    label = f"{contract_name[:30]}|Clean|R{repeat_idx}"
    async with sem:
        logger.info(f"[START] {label}")
        t0 = time.monotonic()
        try:
            g = graph.model_copy(deep=True)
            g = add_medium_implicit_edges(g)
            g = TarjanSCCDetector().detect(g)

            if not g.sccs:
                return {"label": label, "contract": contract_name,
                        "category": "Clean", "repeat": repeat_idx, "error": "no_scc"}

            best_scc = max(g.sccs, key=lambda s: s.size)
            if best_scc.size < 2:
                return {"label": label, "contract": contract_name,
                        "category": "Clean", "repeat": repeat_idx, "error": "scc_too_small"}

            result = await run_mcgs(llm_client, g, config, best_scc)
            elapsed = time.monotonic() - t0

            oc = set(result.get("oc_detected_clauses", []))
            ranking = result.get("ranking_by_risk", [])
            n_nodes = len(best_scc.clause_ids)

            logger.info(f"[DONE] {label} ({elapsed:.0f}s) — SCC={n_nodes}, OC={len(oc)}")
            return {
                "label": label, "contract": contract_name,
                "category": "Clean", "repeat": repeat_idx,
                "scc_nodes": n_nodes, "oc_count": len(oc),
                "avg_risk": round(sum(s for _, s in ranking) / max(n_nodes, 1), 4),
                "llm_calls": result.get("llm_calls", 0),
                "time": round(elapsed, 1),
                "detected": False,
            }
        except Exception as e:
            logger.error(f"[FAIL] {label}: {e}")
            return {"label": label, "contract": contract_name,
                    "category": "Clean", "repeat": repeat_idx, "error": str(e)}


# =====================================================================
# Main
# =====================================================================

async def main():
    logger.info("=" * 80)
    logger.info("CLAUSE BATTLE: SA-MCGS vs LLM Baselines on CUAD")
    logger.info("=" * 80)

    os.environ["XHUB_API_KEY"] = os.environ.get("XHUB_API_KEY", "")
    config = {
        "llm": {
            "provider": "openai",
            "model": "deepseek-chat",
            "base_url": "https://api3.xhub.chat/v1",
            "api_key_env": "XHUB_API_KEY",
            "max_concurrent_calls": 8,
            "timeout": 120,
        }
    }

    if not os.environ.get("XHUB_API_KEY"):
        api_key = input("Enter xhub API key: ").strip()
        os.environ["XHUB_API_KEY"] = api_key

    llm_client = OpenAIClient(config["llm"])

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = []

    for contract_name in TARGET_CONTRACTS:
        logger.info(f"Loading graph: {contract_name[:50]}...")
        try:
            graph = load_contract_graph(contract_name)
        except Exception as e:
            logger.error(f"Failed to load {contract_name}: {e}")
            continue

        logger.info(f"  Clauses: {len(graph.clauses)}, Edges: {len(graph.edges)}")

        for repeat in range(1, NUM_REPEATS + 1):
            tasks.append(run_clean(llm_client, graph, config, contract_name, repeat, sem))

        for category in PERTURBATION_CATEGORIES:
            perts = find_clause_perturbations(contract_name, category)
            if not perts:
                logger.warning(f"  No {category} perturbations found for {contract_name[:40]}")
                continue
            logger.info(f"  {category}: {len(perts)} perturbations")

            for pidx, pert in enumerate(perts):
                for repeat in range(1, NUM_REPEATS + 1):
                    tasks.append(run_one(
                        llm_client, graph, config,
                        contract_name, category, pidx, pert, repeat, sem,
                    ))

    total = len(tasks)
    logger.info(f"Total experiments: {total}")
    logger.info("Launching...")

    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r is not None]

    out_path = RESULTS_DIR / "clause_battle.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    logger.info(f"Raw results → {out_path}")

    # ── Print results ──
    ok_results = [r for r in results if "error" not in r]
    err_results = [r for r in results if "error" in r]
    inj_results = [r for r in ok_results if r.get("category") != "Clean"]
    clean_results = [r for r in ok_results if r.get("category") == "Clean"]

    print("\n" + "=" * 120)
    print(f"CLAUSE BATTLE RESULTS — {len(ok_results)} ok, {len(err_results)} errors")
    print("=" * 120)

    if inj_results:
        total_detected = sum(1 for r in inj_results if r.get("detected"))
        total_target_hit = sum(1 for r in inj_results if r.get("target_hit"))
        total_contra_hit = sum(1 for r in inj_results if r.get("contra_hit"))
        total_in_top5 = sum(1 for r in inj_results if r.get("target_in_top5") or r.get("contra_in_top5"))

        n = len(inj_results)
        print(f"\n{'='*80}")
        print(f"AGGREGATE DETECTION (injection runs only, n={n})")
        print(f"{'='*80}")
        print(f"  Detection rate (any signal):   {total_detected}/{n} = {total_detected/n*100:.1f}%")
        print(f"  Target in subgraph:            {total_target_hit}/{n} = {total_target_hit/n*100:.1f}%")
        print(f"  Contradicted node in subgraph: {total_contra_hit}/{n} = {total_contra_hit/n*100:.1f}%")
        print(f"  Target/Contra in top-5:        {total_in_top5}/{n} = {total_in_top5/n*100:.1f}%")

        # Per-category breakdown
        print(f"\n{'='*80}")
        print(f"PER-CATEGORY BREAKDOWN")
        print(f"{'='*80}")
        print(f"{'Category':<30} | {'N':>3} | {'Detected':>8} | {'TargetHit':>9} | {'ContraHit':>9} | {'Top5':>6}")
        print("-" * 80)

        by_cat = defaultdict(list)
        for r in inj_results:
            by_cat[r["category"]].append(r)

        for cat in sorted(by_cat.keys()):
            runs = by_cat[cat]
            k = len(runs)
            det = sum(1 for r in runs if r.get("detected"))
            th = sum(1 for r in runs if r.get("target_hit"))
            ch = sum(1 for r in runs if r.get("contra_hit"))
            t5 = sum(1 for r in runs if r.get("target_in_top5") or r.get("contra_in_top5"))
            print(f"{cat:<30} | {k:>3} | {det:>3}/{k} {det/k*100:>4.0f}% | "
                  f"{th:>3}/{k} {th/k*100:>4.0f}% | {ch:>3}/{k} {ch/k*100:>4.0f}% | "
                  f"{t5:>3}/{k} {t5/k*100:>4.0f}%")

        # Battle comparison
        print(f"\n{'='*80}")
        print(f"BATTLE: SA-MCGS vs CLAUSE Baselines (F1 comparison)")
        print(f"{'='*80}")
        sa_mcgs_detection_rate = total_detected / n if n > 0 else 0
        print(f"\n  SA-MCGS detection rate: {sa_mcgs_detection_rate*100:.1f}%")
        print(f"\n  CLAUSE Baselines (from EACL 2026 paper):")
        for model, scores in CLAUSE_BASELINES.items():
            avg_f1 = sum(scores.values()) / len(scores) * 100
            print(f"    {model:<15}: avg F1 = {avg_f1:.1f}%")

    if clean_results:
        avg_oc_clean = sum(r.get("oc_count", 0) for r in clean_results) / len(clean_results)
        print(f"\n  Clean baseline avg OC count: {avg_oc_clean:.1f} (false positive reference)")

    if err_results:
        print(f"\n--- ERRORS ({len(err_results)}) ---")
        for r in err_results[:10]:
            print(f"  {r.get('label', '?')}: {r.get('error', '?')}")

    print(f"\nFull results → {out_path}")
    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
