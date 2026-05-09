"""Cross-domain SA-MCGS: Larger SCC experiment (7-12 nodes)

Standalone script — does NOT modify run_cross_domain.py parameters.
Tests SA-MCGS on larger SCCs to demonstrate scalability beyond 5-node cycles.
Wikipedia uses budget=60 (consistent with OC sensitivity findings).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.models.clause import Clause, ClauseType
from src.models.graph import DependencyGraph, Edge, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.modules.alphago_mcgs import AlphaGoMCGS
from src.llm.openai_client import OpenAIClient

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

XHUB_BASE_URL = "https://api3.xhub.chat/v1"

LLM_CONFIG = {
    "provider": "openai",
    "model": "deepseek-chat",
    "base_url": XHUB_BASE_URL,
    "api_key_env": "XHUB_API_KEY",
    "timeout": 300,
}

BASE_MCGS = {
    "alphago_mcgs": {
        "budget": 30,
        "window_size": 4,
        "concurrency": 4,
        "ucb_exploration_weight": 1.414,
        "ucb_exploration_init": 2.5,
        "temperature": 0.4,
        "max_tokens": 2048,
        "tt_max_reuse": 3,
    },
    "detection": {"alpha": 0.1, "min_rollouts": 6},
}

WIKI_MCGS = {
    "alphago_mcgs": {
        **BASE_MCGS["alphago_mcgs"],
        "budget": 60,
    },
    "detection": {"alpha": 0.1, "min_rollouts": 6},
}

from run_cross_domain import (
    load_debian_graph,
    load_sec_graph,
    _debian_prompt,
    _wikipedia_prompt,
    _sec_prompt,
)

import re
import urllib.request
from src.models.graph import DependencyType


def load_wikipedia_graph_large(min_cycle: int = 7, max_cycle: int = 15, max_select: int = 8):
    """Load Wikipedia cycles specifically targeting larger ones (>=7 nodes)."""
    import time as _time
    print(f"  [Wikipedia] Fetching cycles {min_cycle}-{max_cycle} nodes...")
    all_cycles = []
    for page_num in range(1, 5):
        url = (
            f"https://en.wikipedia.org/w/api.php?action=parse"
            f"&page=User:SDZeroBot/Category%20cycles/{page_num}"
            f"&prop=wikitext&format=json"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SA-MCGS-Research/1.0"})
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read().decode())
            wt = data.get("parse", {}).get("wikitext", {}).get("*", "")
            for line in wt.strip().split("\n"):
                cats = re.findall(r"Category:([^|\]]+)", line.strip())
                if len(cats) >= 2:
                    all_cycles.append(cats)
            _time.sleep(0.5)
        except Exception as e:
            print(f"    Page {page_num}: {e}")

    target = [c for c in all_cycles if min_cycle <= len(c) <= max_cycle]
    selected = target[:max_select]
    print(f"  [Wikipedia] {len(all_cycles)} total, {len(target)} in {min_cycle}-{max_cycle}, selected {len(selected)}")

    clauses = {}
    edges = []
    for cycle in selected:
        for i, cat in enumerate(cycle):
            cid = cat.replace(" ", "_")
            if cid not in clauses:
                clauses[cid] = Clause(
                    id=cid, title=cat,
                    content=(
                        f"Wikipedia category: {cat}. "
                        f"Part of the Wikipedia category hierarchy. "
                        f"Should follow a DAG (subcategory → parent)."
                    ),
                    clause_type=ClauseType.OTHER,
                )
            next_cat = cycle[(i + 1) % len(cycle)].replace(" ", "_")
            edges.append(Edge(
                source=cid, target=next_cat,
                dependency_type=DependencyType.REFERENCES,
                weight=0.8,
                reasoning=f"{cat} is subcategory of {cycle[(i + 1) % len(cycle)]}",
            ))

    print(f"  [Wikipedia] Graph: {len(clauses)} categories, {len(edges)} edges")
    for c in selected:
        print(f"    cycle size={len(c)}: {' → '.join(c[:4])}...")
    return DependencyGraph(clauses=clauses, edges=edges)


async def run_larger_sccs(
    domain_name: str,
    graph: DependencyGraph,
    prompt_fn,
    mcgs_config: dict,
    min_size: int = 7,
    max_size: int = 15,
    max_sccs: int = 3,
) -> dict:
    """Run MCGS on larger SCCs (>=7 nodes)."""
    print(f"\n{'='*60}")
    print(f"  Domain: {domain_name} — targeting {min_size}-{max_size} node SCCs")
    print(f"  Budget: {mcgs_config['alphago_mcgs']['budget']}")
    print(f"{'='*60}")

    detector = TarjanSCCDetector()
    graph = detector.detect(graph)

    scc_sizes = sorted([s.size for s in graph.sccs], reverse=True)
    print(f"  All SCCs: {scc_sizes[:30]}")

    target_sccs = [s for s in graph.sccs if min_size <= s.size <= max_size]
    target_sccs = sorted(target_sccs, key=lambda s: s.size, reverse=True)[:max_sccs]

    if not target_sccs:
        target_sccs = [s for s in graph.sccs if s.size >= 6]
        target_sccs = sorted(target_sccs, key=lambda s: s.size, reverse=True)[:max_sccs]

    if not target_sccs:
        print(f"  WARNING: No SCCs >= {min_size} nodes for {domain_name}")
        return {"domain": domain_name, "error": "no_large_sccs"}

    print(f"  Selected {len(target_sccs)} SCCs: sizes {[s.size for s in target_sccs]}")

    llm = OpenAIClient(LLM_CONFIG)
    results = {
        "domain": domain_name,
        "llm": LLM_CONFIG["model"],
        "api": "xhub",
        "budget": mcgs_config["alphago_mcgs"]["budget"],
        "sccs": [],
    }

    for scc in target_sccs:
        print(f"\n  --- SCC {scc.id} ({scc.size} nodes) ---")
        nodes_preview = scc.clause_ids[:10]
        names = [graph.clauses[c].title for c in nodes_preview if c in graph.clauses]
        print(f"  Nodes: {names}{'...' if scc.size > 10 else ''}")

        mcgs = AlphaGoMCGS(llm_client=llm, config=mcgs_config)
        mcgs._build_focused_prompt = lambda w, _self=mcgs: prompt_fn(_self, w)

        try:
            scc_result = await mcgs.search(graph, scc)
            scc_result["scc_id"] = scc.id
            scc_result["scc_size"] = scc.size
            scc_result["scc_clause_ids"] = scc.clause_ids
            scc_result["node_names"] = {
                cid: graph.clauses[cid].title
                for cid in scc.clause_ids if cid in graph.clauses
            }

            top = scc_result.get("ranking_by_risk", [])[:5]
            print(f"  LLM calls: {scc_result['llm_calls']}, TT hits: {scc_result['tt_hits']}")
            print(f"  OC detected: {scc_result['oc_detected_clauses']}")
            print(f"  Top-5 risk:")
            for cid, score in top:
                name = graph.clauses.get(cid, Clause(id=cid, title=cid, content="")).title
                print(f"    {name}: {score:.3f}")

            results["sccs"].append(scc_result)
        except Exception as e:
            print(f"  ERROR on SCC {scc.id}: {e}")
            import traceback; traceback.print_exc()
            results["sccs"].append({"scc_id": scc.id, "error": str(e)})

    await llm.close()
    return results


async def main():
    api_key = os.environ.get("XHUB_API_KEY", "")
    if not api_key:
        api_key = input("Enter XHUB API key: ").strip()
        os.environ["XHUB_API_KEY"] = api_key
    if not api_key:
        raise RuntimeError("XHUB_API_KEY is required")

    print("=" * 60)
    print("  SA-MCGS: LARGER SCC EXPERIMENT (7-12 nodes)")
    print("  Debian & SEC: budget=30 | Wikipedia: budget=60")
    print("=" * 60)

    all_results = {}

    # Debian — 12n, 11n, 7n available
    try:
        print("\n[1/3] Debian (larger SCCs)...")
        debian_graph = load_debian_graph()
        all_results["debian"] = await run_larger_sccs(
            "Debian Package Dependencies", debian_graph, _debian_prompt,
            BASE_MCGS, min_size=7, max_size=15, max_sccs=3,
        )
    except Exception as e:
        print(f"  Debian FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["debian"] = {"error": str(e)}

    # Wikipedia — lots of 7-15 cycles (custom loader for larger ones)
    try:
        print("\n[2/3] Wikipedia (larger SCCs, budget=60)...")
        wiki_graph = load_wikipedia_graph_large(min_cycle=7, max_cycle=15, max_select=8)
        all_results["wikipedia"] = await run_larger_sccs(
            "Wikipedia Category Hierarchy", wiki_graph, _wikipedia_prompt,
            WIKI_MCGS, min_size=7, max_size=15, max_sccs=3,
        )
    except Exception as e:
        print(f"  Wikipedia FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["wikipedia"] = {"error": str(e)}

    # SEC EX-21 — 12n, 11n, 7n available
    try:
        print("\n[3/3] SEC EX-21 (larger SCCs)...")
        sec_graph = load_sec_graph()
        all_results["sec_ex21"] = await run_larger_sccs(
            "SEC EX-21 Corporate Ownership", sec_graph, _sec_prompt,
            BASE_MCGS, min_size=7, max_size=15, max_sccs=3,
        )
    except Exception as e:
        print(f"  SEC EX-21 FAILED: {e}")
        import traceback; traceback.print_exc()
        all_results["sec_ex21"] = {"error": str(e)}

    # Save
    out = RESULTS_DIR / f"larger_sccs_{int(time.time())}.json"
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nResults saved: {out}")

    # Summary
    print(f"\n{'='*60}\n  SUMMARY\n{'='*60}")
    for domain, res in all_results.items():
        if isinstance(res.get("error"), str):
            print(f"\n  [{domain}] ERROR: {res['error']}")
            continue
        sccs = res.get("sccs", [])
        bgt = res.get("budget", "?")
        print(f"\n  [{domain}] {len(sccs)} SCCs, budget={bgt}")
        for sr in sccs:
            if "error" in sr:
                print(f"    SCC {sr.get('scc_id','?')}: ERROR")
                continue
            n = sr.get("scc_size", "?")
            oc = sr.get("oc_detected_clauses", [])
            names = sr.get("node_names", {})
            top = sr.get("ranking_by_risk", [])[:3]
            print(f"    SCC ({n}n): OC={len(oc)} — top: ", end="")
            print(", ".join(f"{names.get(c,c)}={s:.3f}" for c, s in top))


if __name__ == "__main__":
    asyncio.run(main())
