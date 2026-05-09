"""Human Calibration — 50-100 samples, Cohen's κ.

生成人工标注任务，收集标注后计算 Cohen's kappa 一致性。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from ..models.evaluation import ContractFinalResult
from ..models.graph import DependencyGraph


class HumanCalibration:
    """人机校准评估：生成标注任务 + 计算 Cohen's κ。"""

    def __init__(self, config: dict):
        eval_cfg = config.get("evaluation", {})
        self.sample_size = eval_cfg.get("human_sample_size", 50)
        self.risk_threshold = eval_cfg.get("human_risk_threshold", 0.5)

    def generate_annotation_task(
        self,
        result: ContractFinalResult,
        graph: DependencyGraph,
        output_path: str,
    ) -> dict[str, Any]:
        """生成给人类标注员的标注任务文件。"""
        items = []
        clause_ids = sorted(result.clause_results.keys())

        import random
        sampled = random.sample(clause_ids, min(self.sample_size, len(clause_ids)))

        for cid in sampled:
            clause = graph.clauses.get(cid)
            if not clause:
                continue
            items.append({
                "clause_id": cid,
                "title": clause.title,
                "content": clause.content,
                "instruction": "Rate risk from 0-4: 0=none, 1=low, 2=medium, 3=high, 4=critical",
                "system_score": round(result.clause_results[cid].mean_risk_score, 4),
            })

        task = {
            "task_type": "risk_calibration",
            "num_samples": len(items),
            "items": items,
            "human_labels": {},
        }

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(f"Generated annotation task: {len(items)} samples → {output_path}")
        return {"num_samples": len(items), "output_path": output_path}

    def compute_kappa(
        self,
        result: ContractFinalResult,
        human_labels_path: str,
    ) -> dict[str, Any]:
        """收集人工标注后计算 Cohen's kappa。"""
        data = json.loads(Path(human_labels_path).read_text(encoding="utf-8"))
        human_labels = data.get("human_labels", {})

        if not human_labels:
            return {"error": "No human labels found", "kappa": None}

        sys_binary = []
        human_binary = []

        for cid, human_score in human_labels.items():
            cr = result.clause_results.get(cid)
            if not cr:
                continue
            sys_pred = 1 if cr.mean_risk_score >= self.risk_threshold else 0
            human_pred = 1 if float(human_score) >= 2 else 0
            sys_binary.append(sys_pred)
            human_binary.append(human_pred)

        if len(sys_binary) < 2:
            return {"error": "Not enough paired labels", "kappa": None}

        kappa = self._cohens_kappa(sys_binary, human_binary)

        metrics = {
            "kappa": round(kappa, 4),
            "num_samples": len(sys_binary),
            "interpretation": _interpret_kappa(kappa),
        }
        logger.info(f"Cohen's κ = {kappa:.4f} ({metrics['interpretation']}), n={len(sys_binary)}")
        return metrics

    @staticmethod
    def _cohens_kappa(a: list[int], b: list[int]) -> float:
        n = len(a)
        if n == 0:
            return 0.0
        observed_agreement = sum(1 for x, y in zip(a, b) if x == y) / n
        a1 = sum(a) / n
        b1 = sum(b) / n
        expected_agreement = a1 * b1 + (1 - a1) * (1 - b1)
        if expected_agreement == 1.0:
            return 1.0
        return (observed_agreement - expected_agreement) / (1 - expected_agreement)


def _interpret_kappa(k: float) -> str:
    if k < 0:
        return "poor"
    if k < 0.2:
        return "slight"
    if k < 0.4:
        return "fair"
    if k < 0.6:
        return "moderate"
    if k < 0.8:
        return "substantial"
    return "almost_perfect"
