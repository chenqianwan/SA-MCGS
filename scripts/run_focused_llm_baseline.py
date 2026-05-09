"""Focused LLM Baseline: give SCC node texts directly to LLM for comparison.

Fair comparison: SA-MCGS uses graph-guided MCTS on the same SCC nodes.
This baseline feeds the same node texts directly to the LLM in a single prompt.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm import OpenAIClient
from src.models.graph import DependencyGraph
from src.modules.tarjan import TarjanSCCDetector
from experiments.run_clause_battle import add_medium_implicit_edges
from scripts.analyze_deal_packages import (
    merge_graphs, add_cross_contract_edges, FG_DIR, DEAL_PACKAGES,
)
from scripts.run_deal_clause_ultimate import (
    DEAL_CONTRACT_FILES, DIFFICULTY_TIERS, CLAUSE_BASE,
    load_and_merge, load_clause_perturbations, parse_section_id,
    find_target_in_merged,
)
from src.data.cuad_loader import CUADLoader

CONCURRENCY = 12

PROMPT_TEMPLATE = """You are a senior legal analyst reviewing clauses from related contracts in the same deal.
Below are {n} clauses extracted from a cross-contract dependency cycle (strongly connected component).
Your task: identify which clauses contain contradictions, inconsistencies, structural flaws, 
ambiguities, or omissions that could create legal risk.

{clauses_text}

Instructions:
1. Analyze each clause for internal consistency and cross-clause consistency.
2. Rank ALL clauses by risk level (highest risk first).
3. For each clause, provide a brief risk assessment.

Return a JSON object:
{{
  "risk_ranking": [
    {{"clause_id": "...", "risk_score": 0.0-1.0, "reason": "brief explanation"}},
    ...
  ],
  "detected_issues": ["clause_id_1", "clause_id_2", ...]
}}

Return ONLY the JSON object, no other text."""


async def call_llm(client: OpenAIClient, prompt: str) -> dict | None:
    try:
        resp = await client.call(prompt, temperature=0.1, max_tokens=2000)
        text = resp.content.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        return json.loads(text)
    except Exception as e:
        print(f"  LLM error: {e}")
        return None


async def run_one(client, scc_clauses, perturbed_clauses, label, target_id,
                  tier, difficulty, in_scc, sem):
    async with sem:
        clauses_text = ""
        for cid in sorted(perturbed_clauses.keys()):
            if cid not in scc_clauses:
                continue
            content = perturbed_clauses[cid]
            clauses_text += f"\n--- Clause [{cid}] ---\n{content[:1500]}\n"

        n = sum(1 for cid in scc_clauses if cid in perturbed_clauses)
        prompt = PROMPT_TEMPLATE.format(n=n, clauses_text=clauses_text)

        t0 = time.monotonic()
        result = await call_llm(client, prompt)
        elapsed = time.monotonic() - t0

        if not result:
            result = await call_llm(client, prompt)
            elapsed = time.monotonic() - t0

        if not result:
            print(f"[FAIL] {label}")
            return {"label": label, "tier": tier, "difficulty": difficulty,
                    "target_in_scc": in_scc, "error": "llm_parse_fail"}

        ranking = result.get("risk_ranking", [])
        detected = result.get("detected_issues", [])

        ranked_ids = [r["clause_id"] for r in ranking if "clause_id" in r]
        target_rank = ranked_ids.index(target_id) + 1 if target_id and target_id in ranked_ids else -1
        target_detected = target_id in detected if target_id else False
        target_in_top5 = 0 < target_rank <= 5

        hit = target_detected or target_in_top5
        status = "HIT" if hit else "MISS"
        print(f"[DONE] {label} ({elapsed:.0f}s) — {status}, rank={target_rank}, "
              f"detected={target_detected}, in_scc={in_scc}")

        return {
            "label": label, "tier": tier, "difficulty": difficulty,
            "target_id": target_id, "target_in_scc": in_scc,
            "target_rank": target_rank, "target_detected": target_detected,
            "target_in_top5": target_in_top5, "hit": hit,
            "n_detected": len(detected), "detected_ids": detected,
            "n_clauses": n, "time": round(elapsed, 1),
            "ranking": ranking[:5],
        }


async def main():
    os.environ["XHUB_API_KEY"] = os.environ.get("XHUB_API_KEY", "")
    config = {
        "provider": "openai", "model": "deepseek-chat",
        "base_url": "https://api3.xhub.chat/v1",
        "api_key_env": "XHUB_API_KEY",
        "max_concurrent_calls": 16, "timeout": 60,
    }
    if not os.environ.get("XHUB_API_KEY"):
        api_key = input("Enter xhub API key: ").strip()
        os.environ["XHUB_API_KEY"] = api_key

    client = OpenAIClient(config)
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = []

    for pkg_name in DEAL_CONTRACT_FILES:
        print(f"\nLoading {pkg_name}...")
        graph = load_and_merge(pkg_name)
        if not graph or not graph.sccs:
            continue
        best_scc = max(graph.sccs, key=lambda s: s.size)
        scc_nodes = set(best_scc.clause_ids)
        print(f"  SCC={best_scc.size}: {sorted(scc_nodes)[:6]}...")

        base_clauses = {}
        for cid in scc_nodes:
            c = graph.clauses.get(cid)
            if c:
                base_clauses[cid] = c.content or c.title or cid

        for r in range(1, 3):
            tasks.append(run_one(
                client, scc_nodes, base_clauses,
                f"{pkg_name}|Clean|R{r}", None,
                "clean", "clean", False, sem,
            ))

        for tier_name, (cat_dir, difficulty) in DIFFICULTY_TIERS.items():
            perts = load_clause_perturbations(pkg_name, tier_name, cat_dir)
            for pidx, pert in enumerate(perts):
                prefix = pert["_contract_prefix"]
                loc = pert.get("location", "")
                changed_text = pert.get("changed_text", "")
                sec_id = parse_section_id(loc)
                target_id = find_target_in_merged(graph, sec_id, prefix)
                in_scc = target_id in scc_nodes if target_id else False

                if not in_scc:
                    continue

                perturbed = dict(base_clauses)
                if target_id and changed_text:
                    perturbed[target_id] = changed_text[:1500]

                label = f"{pkg_name}|{tier_name}|{prefix}_{loc[:15]}|P{pidx}"
                for r in range(1, 3):
                    tasks.append(run_one(
                        client, scc_nodes, perturbed,
                        f"{label}R{r}", target_id,
                        tier_name, difficulty, in_scc, sem,
                    ))

    print(f"\nTotal experiments: {len(tasks)}")
    print("Launching...\n")

    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r]

    out = Path("experiments/results/focused_llm_baseline.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))

    # Summary
    print("\n" + "=" * 100)
    print("FOCUSED LLM BASELINE RESULTS")
    print("=" * 100)

    ok = [r for r in results if "error" not in r]
    poisoned = [r for r in ok if r["tier"] != "clean"]
    clean = [r for r in ok if r["tier"] == "clean"]

    if clean:
        avg_det = sum(r["n_detected"] for r in clean) / len(clean)
        print(f"\nClean (n={len(clean)}): avg detected issues = {avg_det:.1f} (false positives)")

    if poisoned:
        hits = sum(1 for r in poisoned if r.get("hit"))
        n = len(poisoned)
        print(f"\nPoisoned in-SCC (n={n}):")
        print(f"  Hit rate: {hits}/{n} = {hits/n*100:.1f}%")

        ranks = [r["target_rank"] for r in poisoned if r.get("target_rank", -1) > 0]
        if ranks:
            print(f"  Avg target rank: {sum(ranks)/len(ranks):.1f}")

        print(f"\n  {'Difficulty':<12} {'Tier':<25} {'N':>3} {'Hit':>6} {'Rate':>6} {'Avg Rank':>9}")
        print(f"  {'-'*70}")
        from collections import defaultdict
        by_tier = defaultdict(list)
        for r in poisoned:
            by_tier[r["tier"]].append(r)
        for tier_name, (_, diff) in DIFFICULTY_TIERS.items():
            runs = by_tier.get(tier_name, [])
            if not runs:
                continue
            h = sum(1 for r in runs if r.get("hit"))
            rks = [r["target_rank"] for r in runs if r.get("target_rank", -1) > 0]
            rk_str = f"{sum(rks)/len(rks):.1f}" if rks else "N/A"
            print(f"  {diff:<12} {tier_name:<25} {len(runs):>3} {h:>3}/{len(runs)} "
                  f"{h/len(runs)*100:>5.0f}% {rk_str:>9}")

    print(f"\n  === COMPARISON ===")
    print(f"  SA-MCGS (graph search):    95.2% detection, avg rank 4.9")
    print(f"  Focused LLM (direct ask):  see above")
    print(f"\nFull results -> {out}")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
