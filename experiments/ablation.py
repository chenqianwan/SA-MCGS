"""Phase 4: Ablation Study.

Runs perturbed graphs under 4 configurations to prove each component contributes:
  1. Full SA-MCGS: graph pruning + three-stage search tree pruning + MCGS
  2. No Graph Pruning: skip Domain-Informed Graph Pruning, rest unchanged
  3. No MCGS (random): pruning active but UCB1 replaced with random branch selection
  4. Direct LLM: single LLM call, no graph structure, no MCGS
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from loguru import logger

from src.llm.base import BaseLLMClient
from src.models.graph import DependencyGraph
from src.pipeline import SaMCGSPipeline

from .perturbation import _deep_copy_graph, _ensure_clause_text
from .runner import _extract_clause_metrics, _run_direct_llm


@dataclass
class AblationResult:
    """Result for one ablation configuration on one perturbation."""
    graph_id: str
    target_clause_id: str
    node_type: str
    perturbation_type: str
    config_name: str            # "full" | "no_graph_pruning" | "no_mcgs" | "direct_llm"

    risk_score: float = 0.0
    max_risk: float = 0.0
    std_risk: float = 0.0
    high_risk_detected: bool = False
    uncertain_detected: bool = False
    time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AblationRunner:
    """Run perturbed graphs under multiple pipeline configurations."""

    CONFIG_NAMES = ["full", "no_graph_pruning", "no_mcgs", "direct_llm"]

    def __init__(
        self,
        base_config: dict,
        llm_client: BaseLLMClient,
        output_dir: str = "experiments/results",
    ):
        self.base_config = base_config
        self.llm_client = llm_client
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[AblationResult] = []
        self.high_risk_threshold = base_config.get("aggregation", {}).get(
            "high_risk_threshold", 0.7
        )

    def _make_config(self, config_name: str) -> dict:
        """Create a modified config for the given ablation variant."""
        cfg = copy.deepcopy(self.base_config)

        if config_name == "no_graph_pruning":
            cfg.setdefault("graph_pruning", {})["enabled"] = False

        elif config_name == "no_mcgs":
            cfg.setdefault("mcgs", {})["ucb_exploration_weight"] = 0.0
            cfg.setdefault("mcgs", {})["num_rollouts"] = 1

        return cfg

    async def run_single(
        self,
        perturbed_graph: DependencyGraph,
        graph_id: str,
        target_clause_id: str,
        node_type: str,
        perturbation_type: str,
        config_name: str,
    ) -> AblationResult:
        """Run one configuration on one perturbed graph."""
        if config_name == "direct_llm":
            clause = perturbed_graph.clauses.get(target_clause_id)
            text = _ensure_clause_text(clause, perturbed_graph) if clause else ""
            score, detected, elapsed = await _run_direct_llm(
                self.llm_client, text, target_clause_id, self.high_risk_threshold
            )
            res = AblationResult(
                graph_id=graph_id,
                target_clause_id=target_clause_id,
                node_type=node_type,
                perturbation_type=perturbation_type,
                config_name=config_name,
                risk_score=score,
                max_risk=score,
                std_risk=0.0,
                high_risk_detected=detected,
                uncertain_detected=False,
                time_seconds=elapsed,
            )
        else:
            cfg = self._make_config(config_name)
            pipeline = SaMCGSPipeline(cfg, self.llm_client)
            g = _deep_copy_graph(perturbed_graph)

            t0 = time.monotonic()
            result = await pipeline.run_from_graph(g, graph_id=f"{graph_id}_{config_name}")
            elapsed = time.monotonic() - t0

            metrics = _extract_clause_metrics(result, target_clause_id)
            res = AblationResult(
                graph_id=graph_id,
                target_clause_id=target_clause_id,
                node_type=node_type,
                perturbation_type=perturbation_type,
                config_name=config_name,
                risk_score=metrics["risk_score"],
                max_risk=metrics["max_risk"],
                std_risk=metrics["std"],
                high_risk_detected=metrics["high_risk"],
                uncertain_detected=metrics["uncertain"],
                time_seconds=elapsed,
            )

        self.results.append(res)
        logger.info(
            f"  [{config_name}] risk={res.risk_score:.3f}, "
            f"detected={res.high_risk_detected or res.uncertain_detected}"
        )
        return res

    async def run_all_configs(
        self,
        perturbed_graph: DependencyGraph,
        graph_id: str,
        target_clause_id: str,
        node_type: str,
        perturbation_type: str,
    ) -> list[AblationResult]:
        """Run all 4 ablation configs on one perturbed graph."""
        results = []
        for cfg_name in self.CONFIG_NAMES:
            logger.info(f"=== Ablation: {cfg_name} | {perturbation_type} on {target_clause_id} ===")
            res = await self.run_single(
                perturbed_graph, graph_id, target_clause_id,
                node_type, perturbation_type, cfg_name,
            )
            results.append(res)
        return results

    def save_results(self, filename: str = "ablation_results.json") -> Path:
        """Save all results."""
        out = self.output_dir / filename
        data = [r.to_dict() for r in self.results]
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        logger.info(f"Saved {len(data)} ablation results to {out}")
        return out

    def compute_detection_rates(self) -> dict[str, dict[str, Any]]:
        """Compute detection rates grouped by config_name x perturbation_type."""
        from collections import defaultdict
        groups: dict[str, list[AblationResult]] = defaultdict(list)
        for r in self.results:
            key = f"{r.config_name}_{r.perturbation_type}"
            groups[key].append(r)

        summary = {}
        for key, group in sorted(groups.items()):
            n = len(group)
            detected = sum(1 for r in group if r.high_risk_detected or r.uncertain_detected)
            summary[key] = {
                "count": n,
                "detection_rate": detected / n if n > 0 else 0,
                "avg_risk_score": sum(r.risk_score for r in group) / n if n > 0 else 0,
            }
        return summary
