from __future__ import annotations

from statistics import mean


def compute_agreement(scores_a: list[float], scores_b: list[float], tolerance: float = 0.1) -> float:
    """计算两组评分的一致率（在 tolerance 内视为一致）"""
    if len(scores_a) != len(scores_b) or not scores_a:
        return 0.0
    agreed = sum(1 for a, b in zip(scores_a, scores_b) if abs(a - b) <= tolerance)
    return agreed / len(scores_a)


def compute_rank_correlation(scores_a: list[float], scores_b: list[float]) -> float:
    """Spearman 秩相关系数"""
    n = len(scores_a)
    if n < 2:
        return 0.0

    def _rank(values: list[float]) -> list[float]:
        sorted_indices = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        for rank, idx in enumerate(sorted_indices):
            ranks[idx] = float(rank)
        return ranks

    ranks_a = _rank(scores_a)
    ranks_b = _rank(scores_b)

    d_squared = sum((ra - rb) ** 2 for ra, rb in zip(ranks_a, ranks_b))
    return 1.0 - (6.0 * d_squared) / (n * (n * n - 1))
