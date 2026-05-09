"""Phase 2: Experiment Runner.

Automates baseline vs. perturbation comparison:
  1. Run SA-MCGS on original graph (baseline)
  2. Run SA-MCGS on perturbed graph
  3. Run direct LLM evaluation on perturbed clause (no graph context)
  4. Record ExperimentResult with all metrics and deltas
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from loguru import logger

from src.llm.base import BaseLLMClient
from src.models.clause import ClauseEvaluation
from src.models.evaluation import ContractFinalResult
from src.models.graph import DependencyGraph
from src.pipeline import SaMCGSPipeline

from .perturbation import (
    _deep_copy_graph,
    _ensure_clause_text,
    perturb_type_a,
    perturb_type_b,
    perturb_type_c,
)


@dataclass
class ExperimentResult:
    """Single experiment result: one perturbation on one target."""

    graph_id: str
    target_clause_id: str
    node_type: str                      # "dag" | "scc"
    scc_id: str | None = None
    perturbation_type: str = "none"     # "none" | "type_a" | "type_b" | "type_c"

    # SA-MCGS full pipeline metrics
    mcgs_risk_score: float = 0.0
    mcgs_max_risk: float = 0.0
    mcgs_std: float = 0.0
    mcgs_reward_mean: float = 0.0
    mcgs_reward_std: float = 0.0
    mcgs_high_risk_detected: bool = False
    mcgs_uncertain_detected: bool = False

    # Direct LLM baseline
    direct_llm_risk_score: float = 0.0
    direct_llm_detected: bool = False

    # Timing
    mcgs_time_seconds: float = 0.0
    direct_llm_time_seconds: float = 0.0

    # Delta fields (perturbation - baseline)
    delta_mcgs_risk: float = 0.0
    delta_mcgs_max: float = 0.0
    delta_mcgs_std: float = 0.0
    delta_direct_llm_risk: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_clause_metrics(
    result: ContractFinalResult,
    clause_id: str,
) -> dict[str, Any]:
    """Extract per-clause metrics from a ContractFinalResult."""
    cr = result.clause_results.get(clause_id)
    if cr is None:
        return {
            "risk_score": 0.0,
            "max_risk": 0.0,
            "std": 0.0,
            "high_risk": False,
            "uncertain": False,
        }
    return {
        "risk_score": cr.mean_risk_score,
        "max_risk": cr.max_risk_score,
        "std": cr.std_risk_score,
        "high_risk": clause_id in result.high_risk_clauses,
        "uncertain": clause_id in result.uncertain_clauses,
    }


def _extract_search_stats(result: ContractFinalResult) -> dict[str, float]:
    """Extract MCGS reward statistics."""
    ss = result.search_statistics
    return {
        "reward_mean": float(ss.get("avg_reward", 0.0)),
        "reward_std": 0.0,  # computed from rollout data if available
    }


async def _run_direct_llm(
    llm_client: BaseLLMClient,
    clause_text: str,
    clause_id: str,
    high_risk_threshold: float = 0.7,
) -> tuple[float, bool, float]:
    """Evaluate a single clause with LLM (no graph context, temperature=0)."""
    prompt = (
        "You are a legal risk assessor. Evaluate the following legal provision "
        "for potential risks, inconsistencies, or problematic language.\n\n"
        f"## Provision\n{clause_text}\n\n"
        "## Task\n"
        "Rate the risk level from 0.0 (no risk) to 1.0 (extreme risk).\n"
        "Provide:\n"
        "1. overall_risk_score: float 0.0-1.0\n"
        "2. reasoning: 1-2 sentence explanation\n\n"
        "Output as JSON: {\"overall_risk_score\": 0.0, \"reasoning\": \"...\"}"
    )
    t0 = time.monotonic()
    try:
        data = await llm_client.call_json(prompt, temperature=0.0)
        score = float(data.get("overall_risk_score", 0.5))
    except Exception as e:
        logger.warning(f"Direct LLM failed for {clause_id}: {e}")
        score = 0.5
    elapsed = time.monotonic() - t0
    detected = score >= high_risk_threshold
    return score, detected, elapsed


class ExperimentRunner:
    """Orchestrates baseline vs. perturbation experiments."""

    def __init__(
        self,
        config: dict,
        llm_client: BaseLLMClient,
        output_dir: str = "experiments/results",
    ):
        self.config = config
        self.llm_client = llm_client
        self.pipeline = SaMCGSPipeline(config, llm_client)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.high_risk_threshold = config.get("aggregation", {}).get(
            "high_risk_threshold", 0.7
        )
        self.results: list[ExperimentResult] = []

    async def run_single(
        self,
        graph: DependencyGraph,
        graph_id: str,
        target_clause_id: str,
        node_type: str,
        perturbation_type: str,
        scc_node_ids: list[str] | None = None,
        clause_y_id: str | None = None,
    ) -> ExperimentResult:
        """Run one baseline + perturbation experiment pair."""

        scc_id = None
        if scc_node_ids:
            scc_id = f"scc_containing_{target_clause_id}"

        # --- 1. Baseline run ---
        logger.info(f"[Baseline] {graph_id}/{target_clause_id} ({node_type})")
        baseline_graph = _deep_copy_graph(graph)
        t0 = time.monotonic()
        baseline_result = await self.pipeline.run_from_graph(baseline_graph, graph_id=f"{graph_id}_baseline")
        baseline_time = time.monotonic() - t0
        baseline_metrics = _extract_clause_metrics(baseline_result, target_clause_id)

        # --- 2. Perturbation run ---
        if perturbation_type == "none":
            perturbed_graph = _deep_copy_graph(graph)
        elif perturbation_type == "type_a":
            perturbed_graph = perturb_type_a(graph, target_clause_id)
        elif perturbation_type == "type_b":
            if not scc_node_ids or not clause_y_id:
                raise ValueError("type_b requires scc_node_ids and clause_y_id")
            perturbed_graph = perturb_type_b(graph, scc_node_ids, target_clause_id, clause_y_id)
        elif perturbation_type == "type_c":
            if not scc_node_ids:
                raise ValueError("type_c requires scc_node_ids")
            perturbed_graph = perturb_type_c(graph, scc_node_ids, target_clause_id)
        else:
            raise ValueError(f"Unknown perturbation type: {perturbation_type}")

        logger.info(f"[Perturbed-{perturbation_type}] {graph_id}/{target_clause_id}")
        t0 = time.monotonic()
        perturbed_result = await self.pipeline.run_from_graph(
            perturbed_graph, graph_id=f"{graph_id}_{perturbation_type}"
        )
        mcgs_time = time.monotonic() - t0
        perturbed_metrics = _extract_clause_metrics(perturbed_result, target_clause_id)
        search_stats = _extract_search_stats(perturbed_result)

        # --- 3. Direct LLM on both baseline and perturbed ---
        baseline_clause = baseline_graph.clauses.get(target_clause_id)
        baseline_clause_text = _ensure_clause_text(baseline_clause, baseline_graph) if baseline_clause else ""
        llm_baseline_score, _, _ = await _run_direct_llm(
            self.llm_client, baseline_clause_text, target_clause_id, self.high_risk_threshold
        )

        perturbed_clause = perturbed_graph.clauses.get(target_clause_id)
        perturbed_clause_text = _ensure_clause_text(perturbed_clause, perturbed_graph) if perturbed_clause else ""
        llm_score, llm_detected, llm_time = await _run_direct_llm(
            self.llm_client, perturbed_clause_text, target_clause_id, self.high_risk_threshold
        )

        # --- 4. Assemble result ---
        exp = ExperimentResult(
            graph_id=graph_id,
            target_clause_id=target_clause_id,
            node_type=node_type,
            scc_id=scc_id,
            perturbation_type=perturbation_type,
            mcgs_risk_score=perturbed_metrics["risk_score"],
            mcgs_max_risk=perturbed_metrics["max_risk"],
            mcgs_std=perturbed_metrics["std"],
            mcgs_reward_mean=search_stats["reward_mean"],
            mcgs_reward_std=search_stats["reward_std"],
            mcgs_high_risk_detected=perturbed_metrics["high_risk"],
            mcgs_uncertain_detected=perturbed_metrics["uncertain"],
            direct_llm_risk_score=llm_score,
            direct_llm_detected=llm_detected,
            mcgs_time_seconds=mcgs_time,
            direct_llm_time_seconds=llm_time,
            delta_mcgs_risk=perturbed_metrics["risk_score"] - baseline_metrics["risk_score"],
            delta_mcgs_max=perturbed_metrics["max_risk"] - baseline_metrics["max_risk"],
            delta_mcgs_std=perturbed_metrics["std"] - baseline_metrics["std"],
            delta_direct_llm_risk=llm_score - llm_baseline_score,
        )

        self.results.append(exp)
        logger.info(
            f"  Result: mcgs_risk={exp.mcgs_risk_score:.3f} "
            f"(delta={exp.delta_mcgs_risk:+.3f}), "
            f"llm_risk={exp.direct_llm_risk_score:.3f} "
            f"(delta={exp.delta_direct_llm_risk:+.3f})"
        )
        return exp

    async def run_dag_group(
        self,
        graph: DependencyGraph,
        graph_id: str,
        dag_target_ids: list[str],
    ) -> list[ExperimentResult]:
        """Run Type A perturbation on a batch of DAG nodes."""
        results = []
        for i, cid in enumerate(dag_target_ids):
            logger.info(f"=== DAG target {i+1}/{len(dag_target_ids)}: {cid} ===")
            exp = await self.run_single(
                graph, graph_id, cid,
                node_type="dag",
                perturbation_type="type_a",
            )
            results.append(exp)
        return results

    async def run_scc_group(
        self,
        graph: DependencyGraph,
        graph_id: str,
        scc_targets: list[dict[str, Any]],
        perturbation_types: list[str] = ("type_a", "type_b", "type_c"),
    ) -> list[ExperimentResult]:
        """Run all perturbation types on selected SCCs."""
        results = []
        for scc_target in scc_targets:
            scc_node_ids = scc_target["node_ids"]
            scc_id = scc_target["scc_id"]

            for ptype in perturbation_types:
                # Pick target clause(s) within SCC
                target_id = scc_node_ids[0]
                clause_y_id = scc_node_ids[1] if len(scc_node_ids) > 1 else None

                logger.info(f"=== SCC {scc_id}, {ptype}, target={target_id} ===")

                if ptype == "type_b" and clause_y_id is None:
                    logger.warning(f"Skipping type_b for {scc_id}: need at least 2 nodes")
                    continue

                exp = await self.run_single(
                    graph, graph_id, target_id,
                    node_type="scc",
                    perturbation_type=ptype,
                    scc_node_ids=scc_node_ids,
                    clause_y_id=clause_y_id,
                )
                results.append(exp)
        return results

    def save_results(self, filename: str = "experiment_results.json") -> Path:
        """Save all collected results to JSON."""
        out = self.output_dir / filename
        data = [r.to_dict() for r in self.results]
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        logger.info(f"Saved {len(data)} results to {out}")
        return out

    def compute_detection_rates(self) -> dict[str, Any]:
        """Compute summary detection rates grouped by node_type x perturbation_type."""
        from collections import defaultdict
        groups: dict[str, list[ExperimentResult]] = defaultdict(list)
        for r in self.results:
            if r.perturbation_type == "none":
                continue
            key = f"{r.node_type}_{r.perturbation_type}"
            groups[key].append(r)

        summary = {}
        for key, group in sorted(groups.items()):
            n = len(group)
            mcgs_detected = sum(1 for r in group if r.mcgs_high_risk_detected or r.mcgs_uncertain_detected)
            llm_detected = sum(1 for r in group if r.direct_llm_detected)
            avg_delta_mcgs = sum(r.delta_mcgs_risk for r in group) / n if n > 0 else 0
            avg_delta_llm = sum(r.delta_direct_llm_risk for r in group) / n if n > 0 else 0

            summary[key] = {
                "count": n,
                "mcgs_detection_rate": mcgs_detected / n if n > 0 else 0,
                "llm_detection_rate": llm_detected / n if n > 0 else 0,
                "avg_delta_mcgs_risk": round(avg_delta_mcgs, 4),
                "avg_delta_llm_risk": round(avg_delta_llm, 4),
            }
        return summary
