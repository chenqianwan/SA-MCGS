"""Targeted re-run: budget=60 for experiments that failed to trigger OC.

Targets:
  - Debian gpt-4o SA-MCGS: scc_11 (6n) + scc_1 (7n)
  - SEC 11n SA-MCGS: scc_2 (11n) × gpt-4o + deepseek-v3

Results saved with prefix "battle_b60_".
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from src.models.clause import Clause
from src.models.graph import DependencyGraph, SCCInfo
from src.modules.tarjan import TarjanSCCDetector
from src.llm.openai_client import OpenAIClient

from run_cross_domain import load_debian_graph, load_sec_graph
from run_cross_domain_battle import (
    run_sa_mcgs,
    DOMAIN_MCGS_PROMPTS,
    GROUND_TRUTH,
    is_ground_truth_node,
    get_gt_evidence,
    select_sccs,
)

RESULTS_DIR = Path(__file__).parent / "results"
XHUB_BASE_URL = "https://api3.xhub.chat/v1"

MCGS_B60 = {
    "alphago_mcgs": {
        "budget": 60, "window_size": 4, "concurrency": 4,
        "ucb_exploration_weight": 1.414, "ucb_exploration_init": 2.5,
        "temperature": 0.4, "max_tokens": 2048, "tt_max_reuse": 3,
    },
    "detection": {"alpha": 0.1, "min_rollouts": 6},
}

TARGETS = [
    # (domain, scc_content_patterns, model_name, model_id, expected_size_range)
    # patterns: any node in SCC must contain one of these strings (case-insensitive)
    ("debian",   ["libmono"],    "gpt-4o",      "gpt-4o",       (5, 7)),
    ("debian",   ["ruby-sdbm"],  "gpt-4o",      "gpt-4o",       (5, 10)),
    ("sec_ex21", None,           "gpt-4o",      "gpt-4o",       (8, 15)),  # largest SCC
    ("sec_ex21", None,           "deepseek-v3", "deepseek-chat",(8, 15)),  # largest SCC
]


def find_target_scc(
    graph: DependencyGraph,
    patterns: list[str] | None,
    size_range: tuple[int, int],
) -> SCCInfo | None:
    """Find SCC by content patterns or by size range (picks largest)."""
    candidates = [s for s in graph.sccs if size_range[0] <= s.size <= size_range[1]]
    if not candidates:
        return None
    if patterns:
        for scc in candidates:
            if any(
                any(p.lower() in cid.lower() for p in patterns)
                for cid in scc.clause_ids
            ):
                return scc
        return None
    # No patterns: return largest
    return max(candidates, key=lambda s: s.size)


async def main():
    api_key = os.environ.get("XHUB_API_KEY", "")
    if not api_key:
        raise RuntimeError("XHUB_API_KEY not set — check .env")

    print("=" * 60)
    print("  Budget=60 Re-run (4 SA-MCGS experiments)")
    print("=" * 60)

    print("\n[LOAD] Loading Debian + SEC graphs...")
    graphs = {
        "debian":   load_debian_graph(),
        "sec_ex21": load_sec_graph(),
    }

    # Build scc lookup per domain
    for domain, graph in graphs.items():
        detector = TarjanSCCDetector()
        graph = detector.detect(graph)
        graphs[domain] = graph
        print(f"  [{domain}] {len(graph.sccs)} SCCs indexed")

    all_results = []
    total = len(TARGETS)

    for idx, (domain, patterns, model_name, model_id, size_range) in enumerate(TARGETS, 1):
        graph = graphs[domain]
        scc = find_target_scc(graph, patterns, size_range)
        if scc is None:
            desc = f"patterns={patterns}" if patterns else f"largest in {size_range}"
            print(f"\n  [{idx}/{total}] SKIP: no SCC found for {domain} ({desc})")
            continue

        gt_nodes = [c for c in scc.clause_ids if is_ground_truth_node(c, domain)]
        gt_names = [graph.clauses[n].title for n in gt_nodes if n in graph.clauses]

        print(f"\n{'─'*60}")
        print(f"  [{idx}/{total}] {model_name} + SA-MCGS(b60) on {domain} {scc.size}n ({scc.id})")
        print(f"  GT nodes: {gt_names or '(none)'}")
        print(f"{'─'*60}")

        llm = OpenAIClient({
            "provider": "openai",
            "model": model_id,
            "base_url": XHUB_BASE_URL,
            "api_key_env": "XHUB_API_KEY",
            "timeout": 300,
        })

        try:
            result = await run_sa_mcgs(llm, model_name, domain, graph, scc, MCGS_B60)
            top3 = result["ranking"][:3]
            print(f"  Top-3: {[(graph.clauses.get(c, Clause(id=c, title=c, content='')).title, f'{s:.3f}') for c, s in top3]}")
            print(f"  Spread: {result['score_spread']:.3f}  OC: {result['oc_count']}  LLM calls: {result['llm_calls']}  TT: {result['tt_hit_rate']:.0%}")
            print(f"  Top-1 GT: {result['top1_hit']}")
            all_results.append(result)
        except Exception as e:
            print(f"  ERROR: {e}")
            all_results.append({
                "method": "sa-mcgs", "model": model_name, "domain": domain,
                "scc_id": scc_id, "scc_size": scc.size, "budget": 60, "error": str(e),
            })

        await llm.close()

    out_file = RESULTS_DIR / f"battle_b60_{int(time.time())}.json"
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print(f"  Saved: {out_file}")
    print(f"\n  SUMMARY (budget=60 vs budget=30)")
    print(f"{'─'*60}")
    print(f"  {'Domain':<12} {'SCC':<8} {'Model':<14} {'Size':<6} {'OC':>4} {'Spread':>8} {'LLM':>5}")
    print(f"  {'─'*58}")
    for r in all_results:
        if "error" in r:
            print(f"  {r['domain']:<12} {r['scc_id']:<8} {r['model']:<14} {'ERROR'}")
            continue
        print(f"  {r['domain']:<12} {r['scc_id']:<8} {r['model']:<14} {r['scc_size']:<6} {r.get('oc_count',0):>4} {r['score_spread']:>8.3f} {r.get('llm_calls',0):>5}")


if __name__ == "__main__":
    asyncio.run(main())
