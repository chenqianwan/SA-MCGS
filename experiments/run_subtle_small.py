"""Test type_c_subtle perturbation at small scales (5-50 clauses)."""
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

SCALES = [5, 10, 20, 30, 50]
TRIALS = 5
THRESHOLD = 0.7
SEED = 123


def _subtle_perturb(text):
    return (
        f"{text}\n\n"
        "The obligations and rights established herein shall apply, mutatis mutandis, "
        "to all related provisions of this legislation, regardless of any scope limitations "
        "stated therein. Any temporal or subject-matter restrictions in the referenced "
        "provisions shall be deemed inapplicable insofar as they conflict with the "
        "principles established by this section."
    )


def _build_prompt(clauses_text):
    clauses_fmt = "\n\n".join(
        f"### {cid}: {t}\n{c}" for cid, t, c in clauses_text
    )
    cids_json = ", ".join(f'"{cid}"' for cid, _, _ in clauses_text)
    return (
        "You are a legal risk assessor. Evaluate a set of legal provisions "
        "for potential risks, inconsistencies, contradictions, or problematic language.\n\n"
        f"## Legal Provisions ({len(clauses_text)} clauses)\n{clauses_fmt}\n\n"
        "## Task\n"
        "For EACH clause, assign a risk score from 0.0 (no risk) to 1.0 (extreme risk). "
        "Pay special attention to:\n"
        "- Internal contradictions within a clause\n"
        "- Overbroad scope expansion or applicability conflicts\n"
        "- Ambiguous or conflicting temporal/subject-matter restrictions\n\n"
        "Output STRICTLY as JSON (no extra text):\n"
        '{"clause_evaluations": {'
        f'{cids_json}: '
        '{"overall_risk_score": 0.0, "reasoning": "brief reason"}'
        "}}"
    )


async def main():
    with open("config/deepseek.yaml") as f:
        config = yaml.safe_load(f)

    llm = OpenAIClient(config["llm"])
    loader = QuantLawLoader("data/quantlaw", config)
    _, graph = loader.load_single(
        "data/quantlaw/de/4_crossreference_graph/2019.gpickle.gz"
    )
    DomainGraphPruner(config).prune(graph)
    graph = TarjanSCCDetector().detect(graph)

    pool = [
        cid for cid, c in graph.clauses.items()
        if c.content and len(c.content) > 100
    ]
    random.seed(SEED)
    random.shuffle(pool)
    max_tok = config.get("scc", {}).get("max_tokens", 8192)

    all_results = []

    for scale in SCALES:
        logger.info(f"=== SCALE {scale} ===")
        detections = 0
        scores = []
        for trial in range(TRIALS):
            rng = random.Random(SEED + 10000 + scale * 100 + trial)
            sel = rng.sample(pool, min(scale, len(pool)))
            tgt = rng.choice(sel)

            ct = []
            for cid in sel:
                c = graph.clauses[cid]
                content = c.content or ""
                if cid == tgt:
                    content = _subtle_perturb(content)
                ct.append((cid, c.title or cid, content))

            prompt = _build_prompt(ct)
            t0 = time.monotonic()
            try:
                resp = await llm.call_json(prompt, temperature=0.0, max_tokens=max_tok)
                elapsed = time.monotonic() - t0
                raw = resp.get("clause_evaluations", resp)
                td = raw.get(tgt, {})
                if isinstance(td, dict):
                    score = float(td.get("overall_risk_score", 0.0))
                elif isinstance(td, (int, float)):
                    score = float(td)
                else:
                    score = 0.0
            except Exception as e:
                elapsed = time.monotonic() - t0
                logger.warning(f"Failed: {e}")
                score = 0.0

            det = score >= THRESHOLD
            if det:
                detections += 1
            scores.append(score)
            logger.info(
                f"  Trial {trial+1}: target={tgt}, score={score:.3f} "
                f"({'DET' if det else 'MISS'}), time={elapsed:.1f}s"
            )

        rate = detections / TRIALS
        avg = sum(scores) / len(scores)
        all_results.append({"scale": scale, "det_rate": rate, "avg_score": avg})
        logger.info(f"  Summary: DetRate={rate:.0%}, AvgScore={avg:.3f}")

    await llm.close()

    logger.info("\n" + "=" * 50)
    logger.info("FINAL: TYPE C SUBTLE (small scales)")
    logger.info("=" * 50)
    for r in all_results:
        logger.info(f"  {r['scale']:>5} clauses: {r['det_rate']*100:>5.0f}% det, avg={r['avg_score']:.3f}")

    Path("experiments/results/scaling_subtle_small.json").write_text(
        json.dumps(all_results, indent=2)
    )


if __name__ == "__main__":
    asyncio.run(main())
