"""AlphaGo-style MCGS: single-step online greedy search for SCC risk.

Merges sampling and search into one loop. Each iteration:
  1. UCB Selection  — pick a seed node + greedily expand a focus window
  2. Evaluation     — check transposition table; LLM call on miss
  3. Backpropagation — update per-node and per-edge statistics
  4. OC Detection   — self-calibrating anomaly check

Parallelism via Virtual Loss: multiple windows evaluated concurrently;
inflight windows get a virtual penalty so concurrent threads explore
different regions of the graph.

References:
  - Silver et al., "Mastering the game of Go with deep neural networks
    and tree search", Nature 2016 (Virtual Loss, parallel MCTS)
  - Gibbs & Candes, "Adaptive Conformal Inference Under Distribution
    Shift", NeurIPS 2021 (OC detection)
"""
from __future__ import annotations

import asyncio
import math
import random
import time
from collections import defaultdict
from typing import Any, Optional

from loguru import logger

from ..llm.base import BaseLLMClient
from ..models.clause import Clause
from ..models.graph import DependencyGraph, Edge, SCCInfo
from ..models.search_tree import EdgeStats, NodeStats, TranspositionEntry


class AlphaGoMCGS:
    """Single-step AlphaGo-style Monte Carlo Graph Search."""

    def __init__(
        self,
        llm_client: BaseLLMClient,
        config: dict,
    ):
        self.llm = llm_client
        mcgs_cfg = config.get("alphago_mcgs", config.get("mcgs", {}))
        self.budget = mcgs_cfg.get("budget", 60)
        self.window_size = mcgs_cfg.get("window_size", 4)
        self.concurrency = mcgs_cfg.get("concurrency", 6)
        self.exploration_weight = mcgs_cfg.get("ucb_exploration_weight", 1.414)
        self.exploration_weight_init = mcgs_cfg.get("ucb_exploration_init", 2.5)
        self.virtual_loss_weight = mcgs_cfg.get("virtual_loss_weight", 3)
        self.temperature = mcgs_cfg.get("temperature", 0.3)
        self.max_tokens = mcgs_cfg.get("max_tokens", 2048)
        self.tt_max_reuse = mcgs_cfg.get("tt_max_reuse", 3)
        self.dirichlet_alpha = mcgs_cfg.get("dirichlet_alpha", 0.3)
        self.dirichlet_weight = mcgs_cfg.get("dirichlet_weight", 0.25)

        detect_cfg = config.get("detection", {})
        self.conformal_alpha = detect_cfg.get("alpha", 0.1)
        self.min_iters_for_detection = detect_cfg.get("min_rollouts", 8)

        self._node_stats: dict[str, NodeStats] = {}
        self._edge_stats: dict[tuple[str, str], EdgeStats] = {}
        self._transposition_table: dict[frozenset, TranspositionEntry] = {}
        self._tt_use_count: dict[frozenset, int] = {}
        self._detected_clauses: set[str] = set()
        self._detection_log: list[dict] = []
        self._score_pool: list[float] = []

        self._scc_ids: list[str] = []
        self._adjacency: dict[str, list[str]] = defaultdict(list)
        self._reverse_adj: dict[str, list[str]] = defaultdict(list)
        self._edges_set: set[tuple[str, str]] = set()
        self._clauses: dict[str, Clause] = {}
        self._internal_edges: list[Edge] = []

    # ── Public API ──────────────────────────────────────────────────

    async def search(
        self,
        graph: DependencyGraph,
        scc_info: SCCInfo,
    ) -> dict[str, Any]:
        """Run the full AlphaGo-style search on a single SCC."""
        self._init_state(graph, scc_info)
        n = len(self._scc_ids)

        logger.info(
            f"AlphaGoMCGS: starting on {n} clauses, "
            f"budget={self.budget}, window={self.window_size}, "
            f"concurrency={self.concurrency}"
        )

        t0 = time.monotonic()
        sem = asyncio.Semaphore(self.concurrency)
        iteration = 0
        llm_calls = 0
        tt_hits = 0

        batches = math.ceil(self.budget / self.concurrency)
        for batch_idx in range(batches):
            remaining = self.budget - iteration
            batch_size = min(self.concurrency, remaining)
            if batch_size <= 0:
                break

            async def run_one(iter_idx):
                nonlocal llm_calls, tt_hits
                async with sem:
                    window = self._select_and_expand(iter_idx)
                    self._apply_virtual_loss(window)
                    try:
                        result, is_hit = await self._evaluate(window)
                        if is_hit:
                            tt_hits += 1
                        else:
                            llm_calls += 1
                        self._backpropagate(window, result)
                        self._update_oc(iter_idx)
                    finally:
                        self._remove_virtual_loss(window)

            tasks = [run_one(iteration + i) for i in range(batch_size)]
            await asyncio.gather(*tasks)
            iteration += batch_size

            if batch_idx % 5 == 0 and batch_idx > 0:
                logger.debug(
                    f"  batch {batch_idx}: iter={iteration}/{self.budget}, "
                    f"llm={llm_calls}, tt_hits={tt_hits}, "
                    f"detected={len(self._detected_clauses)}"
                )

        elapsed = time.monotonic() - t0

        result = self._build_result(elapsed, llm_calls, tt_hits, iteration)
        logger.info(
            f"AlphaGoMCGS complete: {iteration} iters, "
            f"{llm_calls} LLM calls, {tt_hits} TT hits, "
            f"detected={len(self._detected_clauses)}, "
            f"time={elapsed:.1f}s"
        )
        return result

    @property
    def detected_clauses(self) -> set[str]:
        return self._detected_clauses

    @property
    def detection_log(self) -> list[dict]:
        return self._detection_log

    @property
    def node_stats(self) -> dict[str, NodeStats]:
        return self._node_stats

    @property
    def edge_stats(self) -> dict[tuple[str, str], EdgeStats]:
        return self._edge_stats

    # ── Initialization ──────────────────────────────────────────────

    def _init_state(self, graph: DependencyGraph, scc_info: SCCInfo):
        self._scc_ids = list(scc_info.clause_ids)
        self._clauses = {cid: graph.clauses[cid] for cid in self._scc_ids if cid in graph.clauses}
        self._internal_edges = [
            e for e in graph.edges
            if e.source in self._clauses and e.target in self._clauses
        ]

        self._adjacency = defaultdict(list)
        self._reverse_adj = defaultdict(list)
        self._edges_set = set()
        for e in self._internal_edges:
            self._adjacency[e.source].append(e.target)
            self._reverse_adj[e.target].append(e.source)
            self._edges_set.add((e.source, e.target))

        self._node_stats = {
            cid: NodeStats(clause_id=cid) for cid in self._scc_ids
        }
        self._edge_stats = {
            (e.source, e.target): EdgeStats(source=e.source, target=e.target)
            for e in self._internal_edges
        }
        self._transposition_table = {}
        self._tt_use_count = {}
        self._detected_clauses = set()
        self._detection_log = []
        self._score_pool = []

    # ── Selection + Window Expansion ────────────────────────────────

    def _select_and_expand(self, iteration: int) -> list[str]:
        seed = self._ucb_select_seed(iteration)
        window = [seed]
        c = self._get_exploration_weight(iteration)

        for _ in range(self.window_size - 1):
            candidates = []
            window_set = set(window)
            for node in window:
                for neighbor in self._adjacency[node]:
                    if neighbor not in window_set:
                        candidates.append((node, neighbor))
                for neighbor in self._reverse_adj[node]:
                    if neighbor not in window_set:
                        candidates.append((neighbor, node))

            if not candidates:
                remaining = [c for c in self._scc_ids if c not in window_set]
                if remaining:
                    window.append(random.choice(remaining))
                break

            noise = [random.gammavariate(self.dirichlet_alpha, 1) for _ in candidates]
            noise_sum = sum(noise) + 1e-8
            noise = [x / noise_sum for x in noise]

            best_edge = None
            best_ucb = -math.inf
            total_visits = max(1, sum(
                self._edge_stats[e].visit_count
                for e in candidates if e in self._edge_stats
            ))

            for idx, edge in enumerate(candidates):
                es = self._edge_stats.get(edge)
                if es is None:
                    ucb = float("inf")
                else:
                    vc = es.visit_count + es.virtual_loss * self.virtual_loss_weight
                    exploit = es.avg_conflict
                    explore = c * math.sqrt(
                        math.log(total_visits + 1) / (vc + 1e-8)
                    )
                    ucb = exploit + explore

                ucb = (1 - self.dirichlet_weight) * ucb + self.dirichlet_weight * noise[idx] * 5
                if ucb > best_ucb:
                    best_ucb = ucb
                    best_edge = edge

            new_node = best_edge[1] if best_edge[0] in set(window) else best_edge[0]
            window.append(new_node)

        return window

    def _get_exploration_weight(self, iteration: int) -> float:
        """Dynamic exploration: high early (broad), low late (focused)."""
        progress = iteration / max(1, self.budget)
        if progress < 0.4:
            return self.exploration_weight_init
        elif progress < 0.7:
            t = (progress - 0.4) / 0.3
            return self.exploration_weight_init * (1 - t) + self.exploration_weight * t
        return self.exploration_weight

    def _ucb_select_seed(self, iteration: int) -> str:
        total_visits = max(1, sum(ns.visit_count for ns in self._node_stats.values()))
        c = self._get_exploration_weight(iteration)

        n = len(self._scc_ids)
        noise = [random.gammavariate(self.dirichlet_alpha, 1) for _ in range(n)]
        noise_sum = sum(noise) + 1e-8
        noise = [x / noise_sum for x in noise]

        best_node = None
        best_ucb = -math.inf

        for idx, (cid, ns) in enumerate(self._node_stats.items()):
            vc = ns.visit_count + ns.virtual_loss * self.virtual_loss_weight
            if vc == 0:
                ucb = float("inf")
            else:
                exploit = ns.avg_risk
                explore = c * math.sqrt(
                    math.log(total_visits + 1) / (vc + 1e-8)
                )
                ucb = exploit + explore

            ucb = (1 - self.dirichlet_weight) * ucb + self.dirichlet_weight * noise[idx] * 10
            if ucb > best_ucb:
                best_ucb = ucb
                best_node = cid

        return best_node

    # ── Virtual Loss ────────────────────────────────────────────────

    def _apply_virtual_loss(self, window: list[str]):
        for cid in window:
            self._node_stats[cid].virtual_loss += 1
        for i in range(len(window) - 1):
            edge = (window[i], window[i + 1])
            rev = (window[i + 1], window[i])
            for e in (edge, rev):
                if e in self._edge_stats:
                    self._edge_stats[e].virtual_loss += 1

    def _remove_virtual_loss(self, window: list[str]):
        for cid in window:
            self._node_stats[cid].virtual_loss = max(0, self._node_stats[cid].virtual_loss - 1)
        for i in range(len(window) - 1):
            edge = (window[i], window[i + 1])
            rev = (window[i + 1], window[i])
            for e in (edge, rev):
                if e in self._edge_stats:
                    self._edge_stats[e].virtual_loss = max(0, self._edge_stats[e].virtual_loss - 1)

    # ── Evaluation (TT + LLM) ──────────────────────────────────────

    async def _evaluate(self, window: list[str]) -> tuple[TranspositionEntry, bool]:
        key = frozenset(window)
        use_count = self._tt_use_count.get(key, 0)
        if key in self._transposition_table and use_count < self.tt_max_reuse:
            self._tt_use_count[key] = use_count + 1
            return self._transposition_table[key], True

        prompt = self._build_focused_prompt(window)
        try:
            resp = await self.llm.call_json(
                prompt, temperature=self.temperature, max_tokens=self.max_tokens
            )
        except Exception as e:
            logger.warning(f"AlphaGoMCGS LLM call failed: {e}")
            resp = {}

        evaluations = {}
        reasonings = {}
        raw_evals = resp.get("clause_evaluations", resp)
        for cid in window:
            if cid in raw_evals and isinstance(raw_evals[cid], dict):
                evaluations[cid] = float(raw_evals[cid].get("risk_score", 0.5))
                reasonings[cid] = str(raw_evals[cid].get("reasoning", ""))[:200]
            else:
                evaluations[cid] = 0.5
                reasonings[cid] = "missing"

        conflicts = resp.get("conflicts", [])
        if not isinstance(conflicts, list):
            conflicts = []

        entry = TranspositionEntry(
            clause_ids=sorted(window),
            clause_evaluations=evaluations,
            clause_reasonings=reasonings,
            conflicts=conflicts,
            timestamp=len(self._transposition_table),
        )
        self._transposition_table[key] = entry
        self._tt_use_count[key] = 0
        return entry, False

    def _build_focused_prompt(self, window: list[str]) -> str:
        clauses_fmt = "\n\n".join(
            f"### {cid}: {self._clauses[cid].title}\n{self._clauses[cid].content}"
            for cid in window if cid in self._clauses
        )

        window_set = set(window)
        relevant_edges = [
            e for e in self._internal_edges
            if e.source in window_set and e.target in window_set
        ]
        deps_fmt = "\n".join(
            f"- {e.source} -> {e.target} ({e.dependency_type.value}): {e.reasoning}"
            for e in relevant_edges
        ) or "No direct dependencies between these clauses."

        clause_ids_json = ", ".join(f'"{cid}"' for cid in window)
        return (
            "You are a legal risk analyst examining a SUBSET of clauses from "
            "a larger system of interdependent legal provisions.\n\n"
            f"## Clauses Under Analysis ({len(window)} of {len(self._scc_ids)} total)\n"
            f"{clauses_fmt}\n\n"
            f"## Dependencies Between These Clauses\n{deps_fmt}\n\n"
            "## Task\n"
            "Analyze whether these clauses contain any logical inconsistency, "
            "scope conflict, or risk amplification when considered together.\n\n"
            "For each clause, assess its risk IN THE CONTEXT of the other "
            "clauses shown. Also identify any specific conflicts between "
            "clause pairs.\n\n"
            "Output STRICTLY as JSON:\n"
            '{"clause_evaluations": {\n'
            + ",\n".join(
                f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief"}}'
                for cid in window
            )
            + '\n},\n'
            '"conflicts": [\n'
            '  {"clause_a": "id", "clause_b": "id", "description": "..."}\n'
            "]}"
        )

    # ── Backpropagation ─────────────────────────────────────────────

    def _backpropagate(self, window: list[str], entry: TranspositionEntry):
        for cid in window:
            score = entry.clause_evaluations.get(cid, 0.5)
            ns = self._node_stats[cid]
            ns.visit_count += 1
            ns.total_risk += score
            ns.risk_history.append(score)
            self._score_pool.append(score)

        conflict_nodes = set()
        for conf in entry.conflicts:
            if isinstance(conf, dict):
                a = conf.get("clause_a", "")
                b = conf.get("clause_b", "")
                if a in self._node_stats:
                    self._node_stats[a].conflict_count += 1
                    conflict_nodes.add(a)
                if b in self._node_stats:
                    self._node_stats[b].conflict_count += 1
                    conflict_nodes.add(b)

        for i in range(len(window)):
            for j in range(i + 1, len(window)):
                for edge in ((window[i], window[j]), (window[j], window[i])):
                    if edge in self._edge_stats:
                        es = self._edge_stats[edge]
                        es.visit_count += 1
                        has_conflict = edge[0] in conflict_nodes and edge[1] in conflict_nodes
                        es.total_conflict += (1.0 if has_conflict else 0.0)

    # ── OC Detection ────────────────────────────────────────────────

    def _update_oc(self, iteration: int):
        if len(self._score_pool) < 10:
            return
        if iteration < self.min_iters_for_detection:
            return

        pool_mean = sum(self._score_pool) / len(self._score_pool)
        pool_std = math.sqrt(
            sum((s - pool_mean) ** 2 for s in self._score_pool) / len(self._score_pool)
        )
        if pool_std < 1e-6:
            return

        sorted_pool = sorted(self._score_pool)
        pool_median = sorted_pool[len(sorted_pool) // 2]

        for cid, ns in self._node_stats.items():
            if cid in self._detected_clauses:
                continue
            if ns.visit_count < self.min_iters_for_detection:
                continue

            scores = ns.risk_history
            clause_mean = sum(scores) / len(scores)

            z_score = (clause_mean - pool_mean) / pool_std
            z_detected = z_score > 1.5

            all_sorted = sorted(scores)
            n_scores = len(all_sorted)
            ranks = []
            for s in scores:
                rank = sum(1 for ps in self._score_pool if ps <= s) / len(self._score_pool)
                ranks.append(rank)
            avg_rank = sum(ranks) / len(ranks)
            rank_detected = avg_rank > 0.8

            exceedance = sum(1 for s in scores if s > pool_median) / len(scores)
            exc_detected = exceedance > 0.8

            votes = sum([z_detected, rank_detected, exc_detected])
            if votes >= 2:
                self._detected_clauses.add(cid)
                self._detection_log.append({
                    "clause_id": cid,
                    "detected_at_iter": iteration,
                    "clause_mean": clause_mean,
                    "pool_mean": pool_mean,
                    "z_score": z_score,
                    "avg_rank": avg_rank,
                    "exceedance": exceedance,
                    "visit_count": ns.visit_count,
                    "conflict_count": ns.conflict_count,
                    "tests": f"z={z_detected},rank={rank_detected},exc={exc_detected}",
                })

    # ── Result Building ─────────────────────────────────────────────

    def _build_result(
        self, elapsed: float, llm_calls: int, tt_hits: int, total_iters: int
    ) -> dict[str, Any]:
        clause_details = {}
        for cid, ns in self._node_stats.items():
            clause_details[cid] = {
                "mean_score": ns.avg_risk,
                "visit_count": ns.visit_count,
                "conflict_count": ns.conflict_count,
                "risk_history": ns.risk_history,
                "is_oc_detected": cid in self._detected_clauses,
            }

        ranked_by_risk = sorted(
            self._node_stats.items(), key=lambda x: -x[1].avg_risk
        )
        ranked_by_conflict = sorted(
            self._node_stats.items(),
            key=lambda x: -(x[1].conflict_count / max(1, x[1].visit_count)),
        )

        conflict_fanout = {}
        for cid in self._scc_ids:
            outgoing = [
                (s, t) for (s, t), es in self._edge_stats.items()
                if s == cid and es.visit_count > 0
            ]
            if outgoing:
                avg_out_conflict = sum(
                    self._edge_stats[e].avg_conflict for e in outgoing
                ) / len(outgoing)
                total_out_conflict = sum(
                    self._edge_stats[e].total_conflict for e in outgoing
                )
            else:
                avg_out_conflict = 0.0
                total_out_conflict = 0.0
            conflict_fanout[cid] = {
                "avg_conflict": avg_out_conflict,
                "total_conflict": total_out_conflict,
                "num_outgoing": len(outgoing),
            }

        ranked_by_fanout = sorted(
            conflict_fanout.items(),
            key=lambda x: (-x[1]["avg_conflict"], -x[1]["total_conflict"]),
        )

        edge_details = {}
        for (src, tgt), es in self._edge_stats.items():
            if es.visit_count > 0:
                edge_details[f"{src}->{tgt}"] = {
                    "source": src,
                    "target": tgt,
                    "visit_count": es.visit_count,
                    "avg_conflict": es.avg_conflict,
                    "total_conflict": es.total_conflict,
                }

        return {
            "total_clauses": len(self._scc_ids),
            "total_iterations": total_iters,
            "llm_calls": llm_calls,
            "tt_hits": tt_hits,
            "tt_hit_rate": tt_hits / max(1, total_iters),
            "oc_detected_clauses": sorted(self._detected_clauses),
            "oc_count": len(self._detected_clauses),
            "clause_details": clause_details,
            "ranking_by_risk": [(cid, ns.avg_risk) for cid, ns in ranked_by_risk],
            "ranking_by_conflict_rate": [
                (cid, ns.conflict_count / max(1, ns.visit_count))
                for cid, ns in ranked_by_conflict
            ],
            "ranking_by_fanout": [
                (cid, info) for cid, info in ranked_by_fanout
            ],
            "conflict_fanout": conflict_fanout,
            "edge_details": edge_details,
            "detection_log": self._detection_log,
            "time": elapsed,
        }
