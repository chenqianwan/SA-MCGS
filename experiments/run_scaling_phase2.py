"""Phase 2 scaling: fine-grained tests around the tipping point (60-200 clauses).

Phase 1 found: 100% at 50, 80% at 80, 60% at 120.
Phase 2 adds intermediate scales and also tests with "subtle" perturbations
(Type C scope expansion) to see if difficulty matters.

We also go much larger (200, 300, 500) to see the full degradation curve.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
from pathlib import Path

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner

SCALES = [60, 100, 150, 200, 300, 500]
TRIALS_PER_SCALE = 5
HIGH_RISK_THRESHOLD = 0.7
SEED = 123


def _subtle_perturb(clause_content: str, clause_id: str) -> str:
    """Type C-like subtle scope expansion: widen applicability without
    obvious contradiction language. This is harder to detect than Type A."""
    scope_replacements = [
        ("dieses Abschnitts", "des gesamten Gesetzbuchs"),
        ("this section", "the entire code"),
        ("this Part", "all Parts of this Act"),
        ("unter diesem Titel", "unter allen Titeln dieses Gesetzes"),
        ("in this chapter", "throughout this act"),
        ("hereunder", "under any provision of this legislation"),
    ]
    modified = False
    text = clause_content
    for narrow, broad in scope_replacements:
        if narrow.lower() in text.lower():
            text = re.sub(re.escape(narrow), broad, text, count=1, flags=re.IGNORECASE)
            modified = True
            break

    if not modified:
        text = (
            f"{text}\n\n"
            f"The obligations and rights established herein shall apply, mutatis mutandis, "
            f"to all related provisions of this legislation, regardless of any scope limitations "
            f"stated therein. Any temporal or subject-matter restrictions in the referenced "
            f"provisions shall be deemed inapplicable insofar as they conflict with the "
            f"principles established by this section."
        )
    return text


def _type_a_perturb(clause_content: str) -> str:
    """Same Type A as phase 1 for comparability."""
    return (
        f"{clause_content} "
        f"This provision is hereby declared void, yet simultaneously remains "
        f"in full force and effect, creating an irreconcilable legal contradiction."
    )


def _build_prompt(clauses_text: list[tuple[str, str, str]]) -> str:
    clauses_fmt = "\n\n".join(
        f"### {cid}: {title}\n{content}"
        for cid, title, content in clauses_text
    )
    clause_ids_json = ", ".join(f'"{cid}"' for cid, _, _ in clauses_text)

    return (
        "You are a legal risk assessor. Evaluate a set of legal provisions "
        "for potential risks, inconsistencies, contradictions, or problematic language.\n\n"
        f"## Legal Provisions ({len(clauses_text)} clauses)\n{clauses_fmt}\n\n"
        "## Task\n"
        "For EACH clause, assign a risk score from 0.0 (no risk) to 1.0 (extreme risk). "
        "Pay special attention to:\n"
        "- Internal contradictions within a clause\n"
        "- Provisions that declare themselves both void and enforceable\n"
        "- Irreconcilable legal contradictions\n"
        "- Overbroad scope expansion or applicability conflicts\n"
        "- Ambiguous or conflicting temporal/subject-matter restrictions\n\n"
        "Output STRICTLY as JSON (no extra text):\n"
        '{"clause_evaluations": {'
        f'{clause_ids_json}: '
        '{"overall_risk_score": 0.0, "reasoning": "brief reason"}'
        "}}"
    )


async def run_one_trial(
    llm_client, graph, clause_pool, scale, trial, perturb_fn, perturb_name, max_tokens, seed
):
    rng = random.Random(seed + scale * 100 + trial)
    selected_ids = rng.sample(clause_pool, min(scale, len(clause_pool)))
    target_id = rng.choice(selected_ids)

    # Deep copy target clause content and perturb
    import copy
    perturbed_contents = {}
    original_content = graph.clauses[target_id].content or ""
    perturbed_contents[target_id] = perturb_fn(original_content) if perturb_name == "type_a" else _subtle_perturb(original_content, target_id)

    clauses_text = []
    total_chars = 0
    for cid in selected_ids:
        c = graph.clauses[cid]
        title = c.title or cid
        content = perturbed_contents.get(cid, c.content or "")
        clauses_text.append((cid, title, content))
        total_chars += len(content)

    est_tokens = total_chars // 3
    prompt = _build_prompt(clauses_text)
    prompt_tokens = len(prompt) // 3

    logger.info(
        f"  [{perturb_name}] Trial {trial+1}/{TRIALS_PER_SCALE}: "
        f"scale={scale}, target={target_id}, ~{est_tokens} content tokens"
    )

    t0 = time.monotonic()
    try:
        resp = await llm_client.call_json(prompt, temperature=0.0, max_tokens=max_tokens)
        elapsed = time.monotonic() - t0

        raw = resp.get("clause_evaluations", resp)
        target_data = raw.get(target_id, {})
        if isinstance(target_data, dict):
            target_score = float(target_data.get("overall_risk_score", 0.0))
        elif isinstance(target_data, (int, float)):
            target_score = float(target_data)
        else:
            target_score = 0.0

        detected = target_score >= HIGH_RISK_THRESHOLD
        parsed_count = sum(1 for cid in selected_ids if cid in raw)
        false_positives = sum(
            1 for cid in selected_ids
            if cid != target_id and cid in raw
            and (isinstance(raw[cid], dict) and float(raw[cid].get("overall_risk_score", 0)) >= HIGH_RISK_THRESHOLD
                 or isinstance(raw[cid], (int, float)) and float(raw[cid]) >= HIGH_RISK_THRESHOLD)
        )

        logger.info(
            f"    -> Score: {target_score:.3f} ({'DETECTED' if detected else 'MISSED'}), "
            f"parsed: {parsed_count}/{scale}, FP: {false_positives}, time: {elapsed:.1f}s"
        )
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error(f"    -> FAILED: {e}")
        target_score = 0.0
        detected = False
        parsed_count = 0
        false_positives = 0

    return {
        "scale": scale,
        "trial": trial,
        "perturb_type": perturb_name,
        "target_id": target_id,
        "target_score": target_score,
        "detected": detected,
        "parsed_count": parsed_count,
        "total_clauses": len(selected_ids),
        "false_positives": false_positives,
        "content_tokens_est": est_tokens,
        "prompt_tokens_est": prompt_tokens,
        "elapsed_seconds": elapsed,
    }


async def run_phase2():
    logger.info("=" * 70)
    logger.info("SCALING PHASE 2: Fine-grained + Subtle perturbation")
    logger.info(f"Scales: {SCALES}, Trials: {TRIALS_PER_SCALE} per scale per perturbation")
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

    clause_pool = [
        cid for cid, c in graph.clauses.items()
        if c.content and len(c.content) > 100
    ]
    random.seed(SEED)
    random.shuffle(clause_pool)
    logger.info(f"Clause pool: {len(clause_pool)} clauses")

    max_tokens = config.get("scc", {}).get("max_tokens", 8192)
    all_results = []

    for perturb_name, perturb_fn in [("type_a", _type_a_perturb), ("type_c_subtle", _subtle_perturb)]:
        logger.info(f"\n{'#'*70}")
        logger.info(f"PERTURBATION: {perturb_name}")
        logger.info(f"{'#'*70}")

        for scale in SCALES:
            logger.info(f"\n{'='*60}")
            logger.info(f"SCALE = {scale} ({perturb_name})")
            logger.info(f"{'='*60}")

            for trial in range(TRIALS_PER_SCALE):
                result = await run_one_trial(
                    llm_client, graph, clause_pool, scale, trial,
                    perturb_fn, perturb_name, max_tokens,
                    SEED if perturb_name == "type_a" else SEED + 10000
                )
                all_results.append(result)

            scale_results = [r for r in all_results if r["scale"] == scale and r["perturb_type"] == perturb_name]
            det_rate = sum(1 for r in scale_results if r["detected"]) / len(scale_results)
            avg_score = sum(r["target_score"] for r in scale_results) / len(scale_results)
            logger.info(f"  Summary: Det={det_rate:.0%}, AvgScore={avg_score:.3f}")

    # Save
    output_path = Path("experiments/results/scaling_phase2.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build summary
    summary = []
    for perturb_name in ["type_a", "type_c_subtle"]:
        for scale in SCALES:
            s_results = [r for r in all_results if r["scale"] == scale and r["perturb_type"] == perturb_name]
            if not s_results:
                continue
            det_count = sum(1 for r in s_results if r["detected"])
            summary.append({
                "perturb_type": perturb_name,
                "scale": scale,
                "trials": len(s_results),
                "detected": det_count,
                "detection_rate": det_count / len(s_results),
                "avg_target_score": sum(r["target_score"] for r in s_results) / len(s_results),
                "avg_time": sum(r["elapsed_seconds"] for r in s_results) / len(s_results),
                "avg_content_tokens": sum(r["content_tokens_est"] for r in s_results) / len(s_results),
            })

    output_data = {
        "experiment": "scaling_phase2",
        "config": {"scales": SCALES, "trials": TRIALS_PER_SCALE, "seed": SEED},
        "summary": summary,
        "trials": all_results,
    }
    output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False))
    logger.info(f"\nSaved to {output_path}")

    # Print combined table
    logger.info("\n" + "=" * 90)
    logger.info("COMBINED SUMMARY")
    logger.info("=" * 90)
    logger.info(f"{'Perturb':>15} | {'Scale':>6} | {'Det Rate':>10} | {'Avg Score':>10} | {'Tokens':>8} | {'Time':>8}")
    logger.info("-" * 90)
    for s in summary:
        logger.info(
            f"{s['perturb_type']:>15} | {s['scale']:>6} | {s['detection_rate']:>9.0%} | "
            f"{s['avg_target_score']:>10.3f} | {s['avg_content_tokens']:>8.0f} | {s['avg_time']:>7.1f}s"
        )

    await llm_client.close()
    return output_data


if __name__ == "__main__":
    asyncio.run(run_phase2())
