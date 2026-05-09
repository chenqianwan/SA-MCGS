"""Scaling experiment: measure Joint LLM detection rate vs clause-set size.

For each scale (number of clauses), we:
  1. Sample a random set of N clauses from the BGB graph
  2. Inject a type_a perturbation (semantic contradiction) into one clause
  3. Call Joint LLM with all N clauses and ask it to evaluate risk
  4. Repeat K trials per scale (different target each time)
  5. Record detection rate, score distribution, and timing

This identifies the "tipping point" where pure LLM attention starts to fail.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path

import yaml
from loguru import logger

from src.llm import OpenAIClient
from src.data.loader import QuantLawLoader
from src.modules.tarjan import TarjanSCCDetector
from src.modules.graph_pruning import DomainGraphPruner
from experiments.perturbation import perturb_type_a

SCALES = [5, 10, 20, 30, 50, 80, 120]
TRIALS_PER_SCALE = 5
HIGH_RISK_THRESHOLD = 0.7
SEED = 42


def _build_scaling_prompt(clauses_text: list[tuple[str, str, str]], compact: bool = True) -> str:
    """Build a prompt for Joint LLM evaluation of N clauses.

    Args:
        clauses_text: list of (clause_id, title, content)
        compact: use compact output format for large sets
    """
    clauses_fmt = "\n\n".join(
        f"### {cid}: {title}\n{content}"
        for cid, title, content in clauses_text
    )
    clause_ids_json = ", ".join(f'"{cid}"' for cid, _, _ in clauses_text)

    if compact or len(clauses_text) > 10:
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
            "- Problematic scope or ambiguity\n\n"
            "Output STRICTLY as JSON (no extra text):\n"
            '{"clause_evaluations": {'
            f'{clause_ids_json}: '
            '{"overall_risk_score": 0.0, "reasoning": "brief reason"}'
            "}}"
        )

    return (
        "You are a legal risk assessor. Evaluate a set of legal provisions "
        "for potential risks, inconsistencies, contradictions, or problematic language.\n\n"
        f"## Legal Provisions ({len(clauses_text)} clauses)\n{clauses_fmt}\n\n"
        "## Task\n"
        "For EACH clause, provide:\n"
        "1. overall_risk_score: float 0.0 to 1.0\n"
        "2. reasoning: 1-2 sentence explanation\n\n"
        "Pay special attention to:\n"
        "- Internal contradictions within a clause\n"
        "- Provisions that declare themselves both void and enforceable\n"
        "- Irreconcilable legal contradictions\n"
        "- Problematic scope or ambiguity\n\n"
        "Output as JSON:\n"
        '{"clause_evaluations": {'
        f'{clause_ids_json}: '
        '{"overall_risk_score": 0.0, "reasoning": "..."}'
        "}}"
    )


async def run_scaling_experiment():
    logger.info("=" * 70)
    logger.info("SCALING EXPERIMENT: Joint LLM Detection Rate vs Clause-Set Size")
    logger.info(f"Scales: {SCALES}, Trials per scale: {TRIALS_PER_SCALE}")
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

    # Pool of clauses with real content (>100 chars)
    clause_pool = [
        cid for cid, c in graph.clauses.items()
        if c.content and len(c.content) > 100
    ]
    random.seed(SEED)
    random.shuffle(clause_pool)
    logger.info(f"Clause pool: {len(clause_pool)} clauses available")

    max_tokens = config.get("scc", {}).get("max_tokens", 8192)

    all_results: list[dict] = []

    for scale in SCALES:
        logger.info(f"\n{'='*60}")
        logger.info(f"SCALE = {scale} clauses")
        logger.info(f"{'='*60}")

        scale_results = []

        for trial in range(TRIALS_PER_SCALE):
            # Sample N clauses, pick a random target to perturb
            rng = random.Random(SEED + scale * 100 + trial)
            selected_ids = rng.sample(clause_pool, min(scale, len(clause_pool)))

            target_id = rng.choice(selected_ids)

            # Perturb the target clause
            perturbed_graph = perturb_type_a(graph, target_id)

            # Build prompt
            clauses_text = []
            total_chars = 0
            for cid in selected_ids:
                c = perturbed_graph.clauses[cid]
                title = c.title or cid
                content = c.content or ""
                clauses_text.append((cid, title, content))
                total_chars += len(content)

            est_tokens = total_chars // 3
            use_compact = scale > 10

            prompt = _build_scaling_prompt(clauses_text, compact=use_compact)
            prompt_tokens = len(prompt) // 3

            logger.info(
                f"  Trial {trial+1}/{TRIALS_PER_SCALE}: "
                f"target={target_id}, "
                f"~{est_tokens} content tokens, "
                f"~{prompt_tokens} prompt tokens"
            )

            # Call LLM
            t0 = time.monotonic()
            try:
                resp = await llm_client.call_json(
                    prompt, temperature=0.0, max_tokens=max_tokens
                )
                elapsed = time.monotonic() - t0

                # Parse result
                raw = resp.get("clause_evaluations", resp)
                target_data = raw.get(target_id, {})
                if isinstance(target_data, dict):
                    target_score = float(target_data.get("overall_risk_score", 0.0))
                elif isinstance(target_data, (int, float)):
                    target_score = float(target_data)
                else:
                    target_score = 0.0

                detected = target_score >= HIGH_RISK_THRESHOLD

                # Count how many clauses got parsed
                parsed_count = sum(
                    1 for cid in selected_ids if cid in raw
                )

                # Collect all scores for analysis
                all_scores = {}
                for cid in selected_ids:
                    d = raw.get(cid, {})
                    if isinstance(d, dict):
                        all_scores[cid] = float(d.get("overall_risk_score", 0.0))
                    elif isinstance(d, (int, float)):
                        all_scores[cid] = float(d)

                # False positive count: non-target clauses scored >= threshold
                false_positives = sum(
                    1 for cid, s in all_scores.items()
                    if cid != target_id and s >= HIGH_RISK_THRESHOLD
                )

                logger.info(
                    f"    -> Score: {target_score:.3f} "
                    f"({'DETECTED' if detected else 'MISSED'}), "
                    f"parsed: {parsed_count}/{scale}, "
                    f"FP: {false_positives}, "
                    f"time: {elapsed:.1f}s"
                )

            except Exception as e:
                elapsed = time.monotonic() - t0
                logger.error(f"    -> LLM FAILED: {e}")
                target_score = 0.0
                detected = False
                parsed_count = 0
                false_positives = 0
                all_scores = {}

            trial_result = {
                "scale": scale,
                "trial": trial,
                "target_id": target_id,
                "target_score": target_score,
                "detected": detected,
                "parsed_count": parsed_count,
                "total_clauses": len(selected_ids),
                "false_positives": false_positives,
                "content_tokens_est": est_tokens,
                "prompt_tokens_est": prompt_tokens,
                "elapsed_seconds": elapsed,
                "all_scores": all_scores,
            }
            scale_results.append(trial_result)
            all_results.append(trial_result)

        # Per-scale summary
        det_rate = sum(1 for r in scale_results if r["detected"]) / len(scale_results)
        avg_score = sum(r["target_score"] for r in scale_results) / len(scale_results)
        avg_fp = sum(r["false_positives"] for r in scale_results) / len(scale_results)
        avg_time = sum(r["elapsed_seconds"] for r in scale_results) / len(scale_results)
        avg_parsed = sum(r["parsed_count"] for r in scale_results) / len(scale_results)

        logger.info(f"\n  === Scale {scale} Summary ===")
        logger.info(f"  Detection Rate: {det_rate:.0%} ({sum(1 for r in scale_results if r['detected'])}/{len(scale_results)})")
        logger.info(f"  Avg Target Score: {avg_score:.3f}")
        logger.info(f"  Avg False Positives: {avg_fp:.1f}")
        logger.info(f"  Avg Parsed: {avg_parsed:.0f}/{scale}")
        logger.info(f"  Avg Time: {avg_time:.1f}s")

    # Save results
    output_dir = Path("experiments/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "scaling_test.json"

    # Build summary table
    summary = []
    for scale in SCALES:
        s_results = [r for r in all_results if r["scale"] == scale]
        det_count = sum(1 for r in s_results if r["detected"])
        summary.append({
            "scale": scale,
            "trials": len(s_results),
            "detected": det_count,
            "detection_rate": det_count / len(s_results) if s_results else 0,
            "avg_target_score": sum(r["target_score"] for r in s_results) / len(s_results) if s_results else 0,
            "avg_false_positives": sum(r["false_positives"] for r in s_results) / len(s_results) if s_results else 0,
            "avg_parsed_ratio": sum(r["parsed_count"] / r["total_clauses"] for r in s_results) / len(s_results) if s_results else 0,
            "avg_time_seconds": sum(r["elapsed_seconds"] for r in s_results) / len(s_results) if s_results else 0,
            "avg_content_tokens": sum(r["content_tokens_est"] for r in s_results) / len(s_results) if s_results else 0,
        })

    output_data = {
        "experiment": "scaling_test",
        "description": "Joint LLM detection rate vs clause-set size",
        "config": {
            "scales": SCALES,
            "trials_per_scale": TRIALS_PER_SCALE,
            "threshold": HIGH_RISK_THRESHOLD,
            "model": config["llm"]["model"],
            "max_tokens": max_tokens,
            "seed": SEED,
        },
        "summary": summary,
        "trials": all_results,
    }
    output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False))
    logger.info(f"\nResults saved to {output_path}")

    # Print final summary table
    logger.info("\n" + "=" * 80)
    logger.info("FINAL SUMMARY: Detection Rate Curve")
    logger.info("=" * 80)
    logger.info(f"{'Scale':>6} | {'Det Rate':>10} | {'Avg Score':>10} | {'Avg FP':>8} | {'Parse%':>8} | {'Tokens':>8} | {'Time':>8}")
    logger.info("-" * 80)
    for s in summary:
        logger.info(
            f"{s['scale']:>6} | "
            f"{s['detection_rate']:>9.0%} | "
            f"{s['avg_target_score']:>10.3f} | "
            f"{s['avg_false_positives']:>8.1f} | "
            f"{s['avg_parsed_ratio']:>7.0%} | "
            f"{s['avg_content_tokens']:>8.0f} | "
            f"{s['avg_time_seconds']:>7.1f}s"
        )

    await llm_client.close()
    return output_data


if __name__ == "__main__":
    asyncio.run(run_scaling_experiment())
