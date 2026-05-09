"""Wikipedia OC sensitivity test: 3 configurations in parallel.

Config A: budget=60, alpha=0.1  (more rollouts, same threshold)
Config B: budget=30, alpha=0.15 (same rollouts, relaxed threshold)
Config C: budget=60, alpha=0.15 (more rollouts + relaxed threshold)

This is a one-off diagnostic script. Does NOT modify run_cross_domain.py.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.clause import Clause, ClauseType
from src.models.graph import DependencyGraph, DependencyType, Edge, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.llm.openai_client import OpenAIClient

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

LLM_CONFIG = {
    "provider": "openai",
    "model": "deepseek-chat",
    "base_url": "https://api3.xhub.chat/v1",
    "api_key_env": "XHUB_API_KEY",
    "timeout": 300,
}

CONFIGS = {
    "A_budget60_alpha10": {
        "alphago_mcgs": {
            "budget": 60, "window_size": 4, "concurrency": 4,
            "ucb_exploration_weight": 1.414, "ucb_exploration_init": 2.5,
            "temperature": 0.4, "max_tokens": 2048, "tt_max_reuse": 3,
        },
        "detection": {"alpha": 0.1, "min_rollouts": 6},
    },
    "B_budget30_alpha15": {
        "alphago_mcgs": {
            "budget": 30, "window_size": 4, "concurrency": 4,
            "ucb_exploration_weight": 1.414, "ucb_exploration_init": 2.5,
            "temperature": 0.4, "max_tokens": 2048, "tt_max_reuse": 3,
        },
        "detection": {"alpha": 0.15, "min_rollouts": 6},
    },
    "C_budget60_alpha15": {
        "alphago_mcgs": {
            "budget": 60, "window_size": 4, "concurrency": 4,
            "ucb_exploration_weight": 1.414, "ucb_exploration_init": 2.5,
            "temperature": 0.4, "max_tokens": 2048, "tt_max_reuse": 3,
        },
        "detection": {"alpha": 0.15, "min_rollouts": 6},
    },
}


def _wikipedia_prompt(self, window: list[str]) -> str:
    clauses_fmt = "\n\n".join(
        f"### Category: {self._clauses[cid].title}\n{self._clauses[cid].content}"
        for cid in window if cid in self._clauses
    )
    window_set = set(window)
    relevant_edges = [
        e for e in self._internal_edges
        if e.source in window_set and e.target in window_set
    ]
    deps_fmt = "\n".join(
        f"- \"{e.source}\" is a subcategory of \"{e.target}\""
        for e in relevant_edges
    ) or "No direct subcategory links between these categories."

    return (
        "You are a Wikipedia taxonomy expert examining a SUBSET of categories from "
        "a CYCLIC subcategory chain. These categories form a loop which is an error — "
        "the category hierarchy should be a DAG (directed acyclic graph).\n\n"
        f"## Categories Under Analysis ({len(window)} of {len(self._scc_ids)} in this cycle)\n"
        f"{clauses_fmt}\n\n"
        f"## Subcategory Links\n{deps_fmt}\n\n"
        "## Task\n"
        "Determine which subcategory link(s) are INCORRECT and cause the cycle. "
        "For each category, assess its error_risk_score (0.0=correctly placed, "
        "1.0=clearly misplaced/causing the cycle). Identify the specific "
        "problematic subcategory links.\n\n"
        "IMPORTANT: Most categories in this cycle are correctly placed. Only 1-2 "
        "categories are truly misplaced. Give those a HIGH score (>0.8) and give "
        "correctly-placed categories a LOW score (<0.3). Be decisive.\n\n"
        "Output STRICTLY as JSON:\n"
        '{"clause_evaluations": {\n'
        + ",\n".join(
            f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief"}}'
            for cid in window
        )
        + '\n},\n"conflicts": [\n'
        '  {"clause_a": "cat_id", "clause_b": "cat_id", "description": "..."}\n'
        "]}"
    )


def load_wikipedia_graph() -> DependencyGraph:
    print("  [Wikipedia] Fetching category cycles from Wikipedia API...")
    all_cycles = []
    for page_num in range(1, 5):
        url = (
            f"https://en.wikipedia.org/w/api.php?action=parse"
            f"&page=User:SDZeroBot/Category%20cycles/{page_num}"
            f"&prop=wikitext&format=json"
        )
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SA-MCGS-Research/1.0'})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode())
            wt = data.get('parse', {}).get('wikitext', {}).get('*', '')
            for line in wt.strip().split('\n'):
                cats = re.findall(r'Category:([^|\]]+)', line.strip())
                if len(cats) >= 2:
                    all_cycles.append(cats)
            time.sleep(0.5)
        except Exception as e:
            print(f"    Page {page_num}: {e}")

    target_cycles = [c for c in all_cycles if 5 <= len(c) <= 15]
    if not target_cycles:
        target_cycles = [c for c in all_cycles if len(c) >= 3]
    selected = target_cycles[:8]
    print(f"  [Wikipedia] {len(all_cycles)} total cycles, selected {len(selected)} for experiment")

    clauses: dict[str, Clause] = {}
    edges: list[Edge] = []
    for cycle in selected:
        for i, cat in enumerate(cycle):
            cid = cat.replace(' ', '_')
            if cid not in clauses:
                clauses[cid] = Clause(
                    id=cid, title=cat,
                    content=(
                        f"Wikipedia category: {cat}. "
                        f"This category is part of the Wikipedia category hierarchy. "
                        f"It should follow a directed acyclic structure (subcategory → parent)."
                    ),
                    clause_type=ClauseType.OTHER,
                )
            next_cat = cycle[(i + 1) % len(cycle)].replace(' ', '_')
            edges.append(Edge(
                source=cid, target=next_cat,
                dependency_type=DependencyType.REFERENCES,
                weight=0.8,
                reasoning=f"{cat} is subcategory of {cycle[(i+1) % len(cycle)]}",
            ))
    print(f"  [Wikipedia] {len(clauses)} categories, {len(edges)} edges")
    return DependencyGraph(clauses=clauses, edges=edges)


async def run_config(config_name: str, mcgs_config: dict, graph: DependencyGraph) -> dict:
    print(f"\n{'='*60}")
    print(f"  Config: {config_name}")
    budget = mcgs_config["alphago_mcgs"]["budget"]
    alpha = mcgs_config["detection"]["alpha"]
    print(f"  budget={budget}, alpha={alpha}")
    print(f"{'='*60}")

    detector = TarjanSCCDetector()
    g = DependencyGraph(clauses=dict(graph.clauses), edges=list(graph.edges))
    g = detector.detect(g)

    target_sccs = [s for s in g.sccs if 5 <= s.size <= 15]
    if not target_sccs:
        target_sccs = [s for s in g.sccs if s.size >= 3]
    target_sccs = sorted(target_sccs, key=lambda s: s.size)[:3]

    print(f"  SCCs: {[s.size for s in target_sccs]}")

    llm = OpenAIClient(LLM_CONFIG)
    results = {"config": config_name, "budget": budget, "alpha": alpha, "sccs": []}

    for scc in target_sccs:
        print(f"\n  --- SCC {scc.id} ({scc.size} nodes) ---")
        mcgs = AlphaGoMCGS(llm_client=llm, config=mcgs_config)
        mcgs._build_focused_prompt = lambda w, _self=mcgs: _wikipedia_prompt(_self, w)

        try:
            scc_result = await mcgs.search(g, scc)
            scc_result["scc_id"] = scc.id
            scc_result["scc_size"] = scc.size
            scc_result["node_names"] = {
                cid: g.clauses[cid].title for cid in scc.clause_ids if cid in g.clauses
            }
            oc = scc_result.get("oc_detected_clauses", [])
            names = scc_result["node_names"]
            top3 = scc_result.get("ranking_by_risk", [])[:3]

            print(f"    LLM calls: {scc_result['llm_calls']}, TT hits: {scc_result['tt_hits']}")
            print(f"    OC detected: {len(oc)} — {[names.get(c,c) for c in oc]}")
            for cid, score in top3:
                print(f"      {names.get(cid,cid)}: {score:.3f}")

            results["sccs"].append(scc_result)
        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback; traceback.print_exc()
            results["sccs"].append({"scc_id": scc.id, "error": str(e)})

    await llm.close()
    return results


async def main():
    api_key = os.environ.get("XHUB_API_KEY", "")
    if not api_key:
        raise RuntimeError("XHUB_API_KEY is required")

    print("=" * 60)
    print("  Wikipedia OC Sensitivity Test — 3 Configs")
    print("=" * 60)

    print("\nLoading Wikipedia data (shared across all configs)...")
    wiki_graph = load_wikipedia_graph()

    all_results = {}
    for config_name, mcgs_config in CONFIGS.items():
        result = await run_config(config_name, mcgs_config, wiki_graph)
        all_results[config_name] = result

    out = RESULTS_DIR / f"wiki_oc_test_{int(time.time())}.json"
    with open(out, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for cn, res in all_results.items():
        total_oc = sum(len(s.get("oc_detected_clauses", [])) for s in res.get("sccs", []) if "error" not in s)
        sccs_with_oc = sum(1 for s in res.get("sccs", []) if len(s.get("oc_detected_clauses", [])) > 0)
        print(f"\n  [{cn}] budget={res['budget']}, alpha={res['alpha']}")
        print(f"    OC triggered: {sccs_with_oc}/3 SCCs, {total_oc} total nodes")
        for s in res.get("sccs", []):
            if "error" in s:
                continue
            oc = s.get("oc_detected_clauses", [])
            names = s.get("node_names", {})
            top1 = s.get("ranking_by_risk", [[None, 0]])[0]
            oc_str = [names.get(c, c) for c in oc] if oc else ["-"]
            print(f"    SCC({s['scc_size']}n): OC={oc_str}, Top1={names.get(top1[0], '?')} {top1[1]:.3f}")

    print(f"\n  Results saved to: {out}")


if __name__ == "__main__":
    asyncio.run(main())
