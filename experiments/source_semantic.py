"""Source Localization via Semantic Fingerprint + LLM Text Reasoning.

Key insight: graph topology fails in SCCs (everyone reaches everyone).
But Type C perturbation leaves TEXTUAL traces — scope expansion keywords.

Two new methods:
  M6: Semantic Fingerprint — scan clause text for scope-expansion phrases
  M7: LLM Text Forensic   — show LLM the actual clause texts and ask
                             "which clause shows signs of modification?"
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner


SCOPE_EXPANSION_PATTERNS = [
    r"des gesamten Gesetzbuchs",
    r"the entire code",
    r"all Parts of this Act",
    r"unter allen Titeln",
    r"throughout this act",
    r"under any provision of this legislation",
    r"mutatis mutandis",
    r"all related provisions",
    r"regardless of any scope limitations",
    r"including but not limited to",
    r"shall apply.*to all",
    r"nicht nur.*sondern auch",
    r"des gesamten Gesetzes",
    r"entire legislation",
]


def load_graph(config):
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz"
    )
    DomainGraphPruner(config).prune(graph)
    return TarjanSCCDetector().detect(graph)


# ── M6: Semantic Fingerprint ────────────────────────────────────────

def m6_semantic_fingerprint(graph, scc_ids, perturbed_graph):
    """Scan each clause in the PERTURBED graph for scope-expansion keywords.
    Compare with the ORIGINAL text to find which clause was modified."""
    scores = []
    for cid in sorted(scc_ids):
        orig = graph.clauses.get(cid)
        pert = perturbed_graph.clauses.get(cid) if perturbed_graph else None

        orig_text = (orig.content or "") if orig else ""
        pert_text = (pert.content or "") if pert else orig_text

        # Count expansion pattern matches in perturbed text
        pattern_hits = 0
        matched_patterns = []
        for pat in SCOPE_EXPANSION_PATTERNS:
            if re.search(pat, pert_text, re.IGNORECASE):
                # Check if this pattern was NOT in original
                if not re.search(pat, orig_text, re.IGNORECASE):
                    pattern_hits += 2  # New pattern = strong signal
                    matched_patterns.append(f"+{pat}")
                else:
                    pattern_hits += 0.5  # Existing pattern
                    matched_patterns.append(f"={pat}")

        # Check for text length change (scope expansion adds text)
        len_diff = len(pert_text) - len(orig_text)
        len_score = 1.0 if len_diff > 50 else 0.5 if len_diff > 20 else 0

        # Check for _perturbed metadata
        meta_flag = 1 if pert and pert.metadata.get("_perturbed") else 0

        total = pattern_hits + len_score
        scores.append({
            "cid": cid,
            "pattern_hits": pattern_hits,
            "len_diff": len_diff,
            "len_score": len_score,
            "total_score": total,
            "matched_patterns": matched_patterns,
            "has_meta": meta_flag,
        })

    scores.sort(key=lambda x: -x["total_score"])
    return scores


# ── M7: LLM Text Forensic ──────────────────────────────────────────

def build_text_forensic_prompt(clauses_text: dict, new_oc: list, scc_size: int):
    """Give the LLM actual clause texts and ask it to identify the modified one."""
    clauses_section = "\n\n".join(
        f"### {cid}\n{text[:500]}{'...' if len(text) > 500 else ''}"
        for cid, text in sorted(clauses_text.items())
    )

    return (
        "You are a legal forensics expert. A set of interdependent German legal clauses "
        f"({scc_size} clauses total) was subtly modified: EXACTLY ONE clause had its scope "
        "expanded (e.g., 'dieses Abschnitts' changed to 'des gesamten Gesetzbuchs', or "
        "a sentence added that extends applicability beyond the original scope).\n\n"
        "An anomaly detection system found that the following nodes became statistically "
        f"anomalous AFTER the modification: {', '.join(new_oc)}\n\n"
        "Below are the CURRENT texts of all clauses in this group. One of them contains "
        "the scope expansion. Identify it.\n\n"
        f"## Clause Texts\n{clauses_section}\n\n"
        "## Task\n"
        "Which clause was modified with a scope expansion? Look for:\n"
        "- Phrases like 'des gesamten Gesetzbuchs', 'the entire code', 'all related provisions'\n"
        "- Text that seems broader than what section-specific laws would normally say\n"
        "- Injected sentences about applicability 'mutatis mutandis' or 'regardless of scope'\n\n"
        "Output STRICTLY as JSON:\n"
        '{"modified_clause": "<clause_id>", "confidence": 0.0-1.0, '
        '"evidence": "quote the suspicious text", '
        '"top3_suspects": ["<id1>", "<id2>", "<id3>"]}'
    )


async def llm_text_forensic(llm_client, prompt):
    try:
        resp = await llm_client.call_json(prompt, temperature=0.0, max_tokens=2048)
        return resp
    except Exception as e:
        logger.warning(f"LLM text forensic failed: {e}")
        return {"modified_clause": "unknown", "confidence": 0, "evidence": str(e), "top3_suspects": []}


async def main():
    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    graph = load_graph(config)

    with open("experiments/results/ablation_suite.json") as f:
        ablation = json.load(f)

    all_cases = []
    for key in ["exp1_cross_scale", "exp2_multi_target", "exp3_repeated"]:
        all_cases.extend(ablation.get(key, []))

    llm_client = OpenAIClient(config["llm"])

    # We need to reconstruct perturbed graphs for M6
    from experiments.perturbation import perturb_type_c

    print("=" * 110)
    print("SEMANTIC SOURCE LOCALIZATION")
    print("  M6: Semantic Fingerprint (keyword scan on perturbed text)")
    print("  M7: LLM Text Forensic (show actual text, ask 'which was modified?')")
    print("=" * 110)

    m6_results = []
    m7_prompts = []

    for case in all_cases:
        target = case["target_id"]
        scc_ids = set(case["scc_clause_ids"])
        label = case["label"]
        new_oc = set(case["pert_mcgs"]["oc_detected_clauses"]) - set(case["clean_mcgs"]["oc_detected_clauses"])

        if not new_oc:
            m6_results.append({"label": label, "target": target, "skip": True})
            continue

        # Reconstruct perturbed graph
        pg = perturb_type_c(graph, list(scc_ids), target)

        # M6: Semantic fingerprint
        m6 = m6_semantic_fingerprint(graph, scc_ids, pg)
        m6_rank = next((i+1 for i, s in enumerate(m6) if s["cid"] == target), len(scc_ids))

        # M7: Build prompt with perturbed text
        clauses_text = {}
        for cid in scc_ids:
            clause = pg.clauses.get(cid)
            clauses_text[cid] = (clause.content or "") if clause else ""

        prompt = build_text_forensic_prompt(clauses_text, sorted(new_oc), len(scc_ids))
        m7_prompts.append((label, target, scc_ids, new_oc, prompt))

        m6_results.append({
            "label": label, "target": target, "scc_size": len(scc_ids),
            "m6_rank": m6_rank,
            "m6_top1": m6[0]["cid"],
            "m6_top5": [(s["cid"], s["total_score"], s["matched_patterns"][:2]) for s in m6[:5]],
            "m6_target_score": next(s for s in m6 if s["cid"] == target),
            "skip": False,
        })

    # Run all M7 LLM calls in parallel
    m7_responses = await asyncio.gather(*[
        llm_text_forensic(llm_client, p[-1]) for p in m7_prompts
    ])

    # Print results
    print(f"\n{'Label':<30} | {'Target':<12} | {'M6 Rank':>8} {'M6 Top1':<12} | "
          f"{'M7 Source':<12} {'M7 Conf':>7} | {'M7 Evidence':<40}")
    print("-" * 130)

    m6_hits = m6_top3 = m6_top5 = 0
    m7_hits = m7_top3 = 0
    total = 0
    m7_idx = 0

    for r in m6_results:
        if r.get("skip"):
            print(f"{r['label']:<30} | {r['target']:<12} | (no new OC — skipped)")
            continue

        total += 1
        m6r = r["m6_rank"]
        if m6r == 1: m6_hits += 1
        if m6r <= 3: m6_top3 += 1
        if m6r <= 5: m6_top5 += 1

        m7 = m7_responses[m7_idx]
        m7_idx += 1
        m7_source = m7.get("modified_clause", "?")
        m7_conf = m7.get("confidence", 0)
        m7_evidence = m7.get("evidence", "")[:60]
        m7_top3_list = m7.get("top3_suspects", [])

        if m7_source == r["target"]: m7_hits += 1
        if r["target"] in m7_top3_list or m7_source == r["target"]: m7_top3 += 1

        m6_mark = "✅" if m6r == 1 else f"#{m6r}"
        m7_mark = "✅" if m7_source == r["target"] else "❌"

        print(f"{r['label']:<30} | {r['target']:<12} | {m6_mark:>8} {r['m6_top1']:<12} | "
              f"{m7_mark} {m7_source:<10} {m7_conf:>5.0%} | {m7_evidence:<40}")

    print("-" * 130)
    print(f"\n{'Method':<40} | {'Top-1':>12} | {'Top-3':>12} | {'Top-5':>12}")
    print("-" * 80)
    print(f"{'M6: Semantic Fingerprint (keywords)':<40} | "
          f"{m6_hits}/{total} ({m6_hits/total:.0%}):>12 | "
          f"{m6_top3}/{total} ({m6_top3/total:.0%}):>12 | "
          f"{m6_top5}/{total} ({m6_top5/total:.0%}):>12")
    print(f"{'M7: LLM Text Forensic (read text)':<40} | "
          f"{m7_hits}/{total} ({m7_hits/total:.0%}):>12 | "
          f"{m7_top3}/{total} ({m7_top3/total:.0%}):>12 | —")

    # Detailed M6 analysis
    print(f"\n{'='*80}")
    print("M6 DETAILED: Semantic Fingerprint Scores")
    print("=" * 80)
    for r in m6_results:
        if r.get("skip"):
            continue
        print(f"\n{r['label']} | target={r['target']}")
        print(f"  Target score: {r['m6_target_score']['total_score']:.1f} "
              f"(patterns={r['m6_target_score']['pattern_hits']:.1f}, "
              f"len_diff={r['m6_target_score']['len_diff']}, "
              f"matched={r['m6_target_score']['matched_patterns']})")
        print(f"  Top 5:")
        for cid, score, pats in r["m6_top5"]:
            marker = " ◀ TARGET" if cid == r["target"] else ""
            print(f"    {cid:<12} score={score:.1f} patterns={pats}{marker}")

    # Detailed M7 analysis
    print(f"\n{'='*80}")
    print("M7 DETAILED: LLM Text Forensic")
    print("=" * 80)
    m7_idx = 0
    for r in m6_results:
        if r.get("skip"):
            continue
        m7 = m7_responses[m7_idx]; m7_idx += 1
        hit = "✅" if m7.get("modified_clause") == r["target"] else "❌"
        print(f"\n{r['label']} | target={r['target']} | LLM says: {m7.get('modified_clause')} {hit}")
        print(f"  Confidence: {m7.get('confidence', 0):.0%}")
        print(f"  Evidence: {m7.get('evidence', '—')[:200]}")
        print(f"  Top3: {m7.get('top3_suspects', [])}")

    # Save
    out_data = {
        "m6_results": [{k: v for k, v in r.items() if k != "m6_target_score"} for r in m6_results],
        "m7_responses": m7_responses,
        "summary": {
            "m6_top1": f"{m6_hits}/{total}", "m6_top3": f"{m6_top3}/{total}", "m6_top5": f"{m6_top5}/{total}",
            "m7_top1": f"{m7_hits}/{total}", "m7_top3": f"{m7_top3}/{total}",
        }
    }
    Path("experiments/results/source_semantic.json").write_text(
        json.dumps(out_data, indent=2, ensure_ascii=False, default=str))
    print(f"\nSaved to experiments/results/source_semantic.json")

    await llm_client.close()


if __name__ == "__main__":
    asyncio.run(main())
