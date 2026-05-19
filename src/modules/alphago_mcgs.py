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
from collections import deque
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
        evidence_cfg = mcgs_cfg.get("evidence", {})
        self.evidence_subgraph_max_ratio = min(
            1.0,
            max(
                0.05,
                float(evidence_cfg.get(
                    "subgraph_max_ratio",
                    mcgs_cfg.get("evidence_subgraph_max_ratio", 0.45),
                )),
            ),
        )
        self.evidence_subgraph_min_nodes = max(
            1,
            int(evidence_cfg.get(
                "subgraph_min_nodes",
                mcgs_cfg.get("evidence_subgraph_min_nodes", 4),
            )),
        )
        self.evidence_pair_memory_max_ratio = min(
            1.0,
            max(
                0.0,
                float(evidence_cfg.get(
                    "pair_memory_max_ratio",
                    mcgs_cfg.get("evidence_pair_memory_max_ratio", 0.65),
                )),
            ),
        )
        self.evidence_pair_memory_min_score = max(
            0.0,
            float(evidence_cfg.get(
                "pair_memory_min_score",
                mcgs_cfg.get("evidence_pair_memory_min_score", 0.42),
            )),
        )
        self.evidence_pair_closure_min_score = max(
            0.0,
            float(evidence_cfg.get(
                "pair_closure_min_score",
                mcgs_cfg.get("evidence_pair_closure_min_score", 0.35),
            )),
        )
        self.evidence_core_min_nodes = max(
            1,
            int(evidence_cfg.get(
                "core_min_nodes",
                mcgs_cfg.get("evidence_core_min_nodes", 2),
            )),
        )
        self.evidence_core_min_relative_score = min(
            1.0,
            max(
                0.05,
                float(evidence_cfg.get(
                    "core_min_relative_score",
                    mcgs_cfg.get("evidence_core_min_relative_score", 0.52),
                )),
            ),
        )
        self.evidence_core_stop_gap = min(
            1.0,
            max(
                0.0,
                float(evidence_cfg.get(
                    "core_stop_gap",
                    mcgs_cfg.get("evidence_core_stop_gap", 0.14),
                )),
            ),
        )
        self.evidence_core_min_score = max(
            0.0,
            float(evidence_cfg.get(
                "core_min_score",
                mcgs_cfg.get("evidence_core_min_score", 0.10),
            )),
        )
        self.evidence_core_tail_relative_score = min(
            1.0,
            max(
                0.0,
                float(evidence_cfg.get(
                    "core_tail_relative_score",
                    mcgs_cfg.get("evidence_core_tail_relative_score", 0.28),
                )),
            ),
        )
        raw_critical_edge_ratio = evidence_cfg.get(
            "critical_pair_core_max_edge_ratio",
            mcgs_cfg.get("critical_pair_core_max_edge_ratio"),
        )
        self.critical_pair_core_max_edge_ratio = (
            None
            if raw_critical_edge_ratio is None
            else min(1.0, max(0.0, float(raw_critical_edge_ratio)))
        )
        self.critical_pair_core_max_edges = max(
            0,
            int(evidence_cfg.get(
                "critical_pair_core_max_edges",
                mcgs_cfg.get("critical_pair_core_max_edges", 0),
            )),
        )
        self.relation_first_enabled = bool(
            evidence_cfg.get(
                "relation_first",
                mcgs_cfg.get("relation_first_evidence", True),
            )
        )
        self.relation_prior_weight = max(
            0.0,
            float(evidence_cfg.get(
                "relation_prior_weight",
                mcgs_cfg.get("relation_prior_weight", 0.85),
            )),
        )
        self.relation_prior_decay = max(
            0.0,
            float(evidence_cfg.get(
                "relation_prior_decay",
                mcgs_cfg.get("relation_prior_decay", 0.35),
            )),
        )
        self.relation_probe_fraction = min(
            1.0,
            max(
                0.0,
                float(evidence_cfg.get(
                    "probe_fraction",
                    mcgs_cfg.get("relation_probe_fraction", 0.30),
                )),
            ),
        )
        self.relation_probe_min_rollouts = max(
            1,
            int(evidence_cfg.get(
                "probe_min_rollouts",
                mcgs_cfg.get("relation_probe_min_rollouts", 4),
            )),
        )
        self.relation_probe_min_score = max(
            0.0,
            float(evidence_cfg.get(
                "probe_min_score",
                mcgs_cfg.get("relation_probe_min_score", 1.0),
            )),
        )
        self.relation_probe_max_history = max(
            1,
            int(evidence_cfg.get(
                "probe_max_history",
                mcgs_cfg.get("relation_probe_max_history", 48),
            )),
        )
        self.critical_pair_ledger_enabled = bool(
            evidence_cfg.get(
                "critical_pair_ledger",
                mcgs_cfg.get("critical_pair_ledger", True),
            )
        )
        self.critical_pair_enter_threshold = min(
            1.0,
            max(
                0.0,
                float(evidence_cfg.get(
                    "critical_pair_enter_threshold",
                    mcgs_cfg.get("critical_pair_enter_threshold", 0.66),
                )),
            ),
        )
        self.critical_pair_exit_threshold = min(
            1.0,
            max(
                0.0,
                float(evidence_cfg.get(
                    "critical_pair_exit_threshold",
                    mcgs_cfg.get("critical_pair_exit_threshold", 0.48),
                )),
            ),
        )
        self.critical_pair_lock_support = max(
            1,
            int(evidence_cfg.get(
                "critical_pair_lock_support",
                mcgs_cfg.get("critical_pair_lock_support", 2),
            )),
        )
        self.critical_pair_revisit_fraction = min(
            1.0,
            max(
                0.0,
                float(evidence_cfg.get(
                    "critical_pair_revisit_fraction",
                    mcgs_cfg.get("critical_pair_revisit_fraction", 0.45),
                )),
            ),
        )
        self.critical_pair_frontier_max_pairs = max(
            1,
            int(evidence_cfg.get(
                "critical_pair_frontier_max_pairs",
                mcgs_cfg.get("critical_pair_frontier_max_pairs", 8),
            )),
        )
        self.critical_pair_core_min_score = min(
            1.0,
            max(
                0.0,
                float(evidence_cfg.get(
                    "critical_pair_core_min_score",
                    mcgs_cfg.get("critical_pair_core_min_score", 0.62),
                )),
            ),
        )
        self.trace_enabled = bool(
            mcgs_cfg.get("trace", False)
            or mcgs_cfg.get("enable_trace", False)
        )

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
        self._local_subgraph_counts: dict[str, int] = {}
        self._repair_entry_counts: dict[str, int] = {}
        self._local_conflict_pair_counts: dict[tuple[str, str], int] = {}
        self._explicit_conflict_pair_counts: dict[tuple[str, str], int] = {}
        self._local_conflict_pair_reasons: dict[tuple[str, str], list[str]] = {}
        self._amaf_node_evidence: dict[str, float] = {}
        self._amaf_edge_evidence: dict[tuple[str, str], float] = {}
        self._path_fragment_evidence: dict[str, float] = {}
        self._relation_probe_history: list[dict[str, Any]] = []
        self._selection_events: list[dict[str, Any]] = []
        self._last_selection_meta: dict[str, Any] = {}
        self._trace_events: list[dict[str, Any]] = []
        self._critical_pair_ledger: dict[tuple[str, str], dict[str, Any]] = {}
        self._critical_revisit_history: list[dict[str, Any]] = []

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
                        self._record_trace(iter_idx, window, result, is_hit)
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
        self._local_subgraph_counts = defaultdict(int)
        self._repair_entry_counts = defaultdict(int)
        self._local_conflict_pair_counts = defaultdict(int)
        self._explicit_conflict_pair_counts = defaultdict(int)
        self._local_conflict_pair_reasons = defaultdict(list)
        self._amaf_node_evidence = defaultdict(float)
        self._amaf_edge_evidence = defaultdict(float)
        self._path_fragment_evidence = defaultdict(float)
        self._relation_probe_history = []
        self._selection_events = []
        self._last_selection_meta = {}
        self._trace_events = []
        self._critical_pair_ledger = {}
        self._critical_revisit_history = []

    # ── Selection + Window Expansion ────────────────────────────────

    def _select_and_expand(self, iteration: int) -> list[str]:
        probe_window = self._select_relation_probe_window(iteration)
        if probe_window:
            return probe_window

        seed = self._ucb_select_seed(iteration)
        window = [seed]
        c = self._get_exploration_weight(iteration)
        expansion_trace: list[dict[str, Any]] = []

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
            best_prior = 0.0
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
                    relation_prior = self._relation_edge_prior(edge, window_set)
                    progressive_bias = self._progressive_relation_bias(
                        relation_prior,
                        es.visit_count,
                    )
                    ucb = exploit + explore + progressive_bias

                ucb = (1 - self.dirichlet_weight) * ucb + self.dirichlet_weight * noise[idx] * 5
                if ucb > best_ucb:
                    best_ucb = ucb
                    best_edge = edge
                    best_prior = self._relation_edge_prior(edge, window_set)

            new_node = best_edge[1] if best_edge[0] in set(window) else best_edge[0]
            window.append(new_node)
            expansion_trace.append({
                "edge": list(best_edge),
                "added_node": new_node,
                "relation_prior": best_prior,
                "ucb": best_ucb,
            })

        self._last_selection_meta = {
            "mode": "ucb_relation_bias" if self.relation_first_enabled else "ucb",
            "seed": seed,
            "seed_relation_prior": self._relation_node_prior(seed),
            "expansion_trace": expansion_trace,
        }
        self._selection_events.append({
            **self._last_selection_meta,
            "iteration": iteration + 1,
            "window": list(window),
        })
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
        best_prior = 0.0

        for idx, (cid, ns) in enumerate(self._node_stats.items()):
            vc = ns.visit_count + ns.virtual_loss * self.virtual_loss_weight
            if vc == 0:
                ucb = float("inf")
            else:
                exploit = ns.avg_risk
                explore = c * math.sqrt(
                    math.log(total_visits + 1) / (vc + 1e-8)
                )
                relation_prior = self._relation_node_prior(cid)
                progressive_bias = self._progressive_relation_bias(
                    relation_prior,
                    ns.visit_count,
                )
                ucb = exploit + explore + progressive_bias

            ucb = (1 - self.dirichlet_weight) * ucb + self.dirichlet_weight * noise[idx] * 10
            if ucb > best_ucb:
                best_ucb = ucb
                best_node = cid
                best_prior = self._relation_node_prior(cid)

        self._last_selection_meta = {
            "mode": "seed_select",
            "seed": best_node,
            "seed_relation_prior": best_prior,
            "ucb": best_ucb,
        }
        return best_node

    # ── Relation-first Evidence Memory ─────────────────────────────

    def _progressive_relation_bias(self, prior: float, visits: int) -> float:
        """Progressive bias from accumulated relation evidence.

        This is AMAF/RAVE-inspired: evidence observed in any rollout can bias
        related future selections, but the bonus decays as the local action is
        itself sampled often enough.
        """
        if not self.relation_first_enabled or prior <= 0:
            return 0.0
        discount = 1.0 + self.relation_prior_decay * math.sqrt(max(0, visits))
        return self.relation_prior_weight * prior / discount

    def _pair_key(self, source: str, target: str) -> tuple[str, str]:
        return tuple(sorted((source, target)))

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _reason_feature_strength(reasons: list[str]) -> dict[str, float]:
        """Extract domain-agnostic critical-pair features from text reasons."""
        text = " ".join(str(reason) for reason in reasons if reason).lower()
        if not text:
            return {
                "severity_strength": 0.0,
                "same_path_strength": 0.0,
                "no_fallback_strength": 0.0,
            }

        severity_terms = (
            "critical",
            "severe",
            "fatal",
            "high-impact",
            "high impact",
            "material",
            "default",
            "termination",
            "terminate",
            "suspend",
            "suspension",
            "acceleration",
            "accelerate",
            "forfeit",
            "loss of",
            "no cure",
            "non-curable",
            "irreversible",
            "blocking",
            "invalidates",
            "void",
        )
        same_path_terms = (
            "same path",
            "same chain",
            "same route",
            "same transaction",
            "same obligation",
            "same dependency",
            "same control",
            "same branch",
            "same category",
            "same upgrade",
            "same entity",
            "same record",
            "same provision",
            "downstream",
            "upstream",
        )
        no_fallback_terms = (
            "no fallback",
            "without fallback",
            "no valid fallback",
            "no cure",
            "without cure",
            "no exception",
            "without exception",
            "cannot be cured",
            "must",
            "required",
            "mandatory",
            "cannot both",
        )

        severity = 1.0 if any(term in text for term in severity_terms) else 0.0
        same_path = 1.0 if any(term in text for term in same_path_terms) else 0.0
        no_fallback = 1.0 if any(term in text for term in no_fallback_terms) else 0.0

        if severity <= 0 and (
            "unrecoverable" in text or "immediately operative" in text
        ):
            severity = 0.85
        if same_path <= 0 and "path" in text:
            same_path = 0.55
        if no_fallback <= 0 and ("must" in text or "shall" in text):
            no_fallback = 0.45

        return {
            "severity_strength": severity,
            "same_path_strength": same_path,
            "no_fallback_strength": no_fallback,
        }

    def _critical_pair_score(self, info: dict[str, Any]) -> float:
        """Stable score for the persistent critical-pair ledger.

        The score favors repeated support, but it cannot become critical from
        frequency alone; a pair also needs semantic incompatibility, same-path
        evidence, severity, or no-fallback language.
        """
        support = int(info.get("support_count", 0))
        explicit = int(info.get("explicit_count", 0))
        support_score = min(1.0, math.log1p(support) / math.log1p(6))
        explicit_score = min(1.0, math.log1p(explicit) / math.log1p(4))
        semantic = float(info.get("semantic_strength", 0.0))
        severity = float(info.get("severity_strength", 0.0))
        same_path = float(info.get("same_path_strength", 0.0))
        no_fallback = float(info.get("no_fallback_strength", 0.0))
        return min(
            1.0,
            0.30 * semantic
            + 0.25 * severity
            + 0.18 * same_path
            + 0.12 * no_fallback
            + 0.10 * support_score
            + 0.05 * explicit_score,
        )

    def _update_critical_pair_ledger(
        self,
        source: str,
        target: str,
        reasons: list[str],
        *,
        explicit_count: int = 0,
        local_count: int = 0,
        window: list[str] | None = None,
        iteration: int | None = None,
        edge_features: dict[str, Any] | None = None,
    ) -> None:
        """Persist pair evidence across rollouts with hysteresis.

        A pair can enter the frontier when one rollout reports a severe
        same-path incompatibility, but it only locks after repeated support.
        Once locked, it is protected by a lower exit threshold so later noisy
        rollouts do not immediately evict it.
        """
        if not self.critical_pair_ledger_enabled:
            return
        if source not in self._node_stats or target not in self._node_stats or source == target:
            return

        key = self._pair_key(source, target)
        now = int(iteration or (len(self._trace_events) + 1))
        edge_features = edge_features or {}
        info = self._critical_pair_ledger.setdefault(
            key,
            {
                "source": key[0],
                "target": key[1],
                "support_count": 0,
                "explicit_count": 0,
                "local_count": 0,
                "first_seen": now,
                "last_seen": now,
                "visit_windows": 0,
                "revisit_count": 0,
                "semantic_strength": 0.0,
                "severity_strength": 0.0,
                "same_path_strength": 0.0,
                "no_fallback_strength": 0.0,
                "state": "observed",
                "reasons": [],
            },
        )

        info["support_count"] = int(info.get("support_count", 0)) + 1
        info["explicit_count"] = int(info.get("explicit_count", 0)) + int(explicit_count)
        info["local_count"] = int(info.get("local_count", 0)) + int(local_count)
        info["last_seen"] = now
        info["visit_windows"] = int(info.get("visit_windows", 0)) + (1 if window else 0)

        if self._last_selection_meta.get("mode") == "critical_pair_revisit":
            meta_pair = self._pair_key(
                str(self._last_selection_meta.get("source", "")),
                str(self._last_selection_meta.get("target", "")),
            )
            if meta_pair == key:
                info["revisit_count"] = int(info.get("revisit_count", 0)) + 1

        clean_reasons = [str(reason)[:300] for reason in reasons if str(reason).strip()]
        for reason in clean_reasons:
            if reason not in info["reasons"] and len(info["reasons"]) < 5:
                info["reasons"].append(reason)

        text_features = self._reason_feature_strength(clean_reasons)
        semantic = max(
            self._semantic_conflict_strength(clean_reasons),
            self._safe_float(edge_features.get("mutual_incompatibility_score")),
            self._safe_float(edge_features.get("incompatibility_score")),
        )
        severity = max(
            text_features["severity_strength"],
            self._safe_float(edge_features.get("severity_score")),
        )
        same_path = max(
            text_features["same_path_strength"],
            self._safe_float(edge_features.get("same_path_score")),
        )
        no_fallback = max(
            text_features["no_fallback_strength"],
            1.0 if edge_features.get("no_fallback") is True else 0.0,
            self._safe_float(edge_features.get("no_fallback_score")),
        )

        info["semantic_strength"] = max(float(info.get("semantic_strength", 0.0)), semantic)
        info["severity_strength"] = max(float(info.get("severity_strength", 0.0)), severity)
        info["same_path_strength"] = max(float(info.get("same_path_strength", 0.0)), same_path)
        info["no_fallback_strength"] = max(float(info.get("no_fallback_strength", 0.0)), no_fallback)
        score = self._critical_pair_score(info)
        info["critical_pair_score"] = score

        previous_state = str(info.get("state", "observed"))
        if (
            score >= self.critical_pair_enter_threshold
            and int(info.get("support_count", 0)) >= self.critical_pair_lock_support
        ):
            info["state"] = "locked"
        elif score >= self.critical_pair_enter_threshold:
            info["state"] = "candidate"
        elif previous_state == "locked" and score >= self.critical_pair_exit_threshold:
            info["state"] = "locked"
        elif previous_state == "candidate" and score >= self.critical_pair_exit_threshold:
            info["state"] = "candidate"
        else:
            info["state"] = "observed"

    def _critical_pair_rows(self) -> list[dict[str, Any]]:
        rows = []
        for key, info in self._critical_pair_ledger.items():
            score = self._critical_pair_score(info)
            rows.append({
                "source": key[0],
                "target": key[1],
                "state": info.get("state", "observed"),
                "critical_pair_score": score,
                "support_count": int(info.get("support_count", 0)),
                "explicit_count": int(info.get("explicit_count", 0)),
                "local_count": int(info.get("local_count", 0)),
                "revisit_count": int(info.get("revisit_count", 0)),
                "semantic_strength": float(info.get("semantic_strength", 0.0)),
                "severity_strength": float(info.get("severity_strength", 0.0)),
                "same_path_strength": float(info.get("same_path_strength", 0.0)),
                "no_fallback_strength": float(info.get("no_fallback_strength", 0.0)),
                "first_seen": int(info.get("first_seen", 0)),
                "last_seen": int(info.get("last_seen", 0)),
                "reasons": list(info.get("reasons", [])),
            })
        state_rank = {"locked": 0, "candidate": 1, "observed": 2}
        rows.sort(
            key=lambda row: (
                state_rank.get(str(row["state"]), 3),
                -float(row["critical_pair_score"]),
                -int(row["support_count"]),
                row["source"],
                row["target"],
            )
        )
        return rows

    def _best_critical_pair_for_revisit(
        self,
        iteration: int,
    ) -> tuple[str, str, float, str] | None:
        if not self.critical_pair_ledger_enabled:
            return None
        if self.critical_pair_revisit_fraction <= 0:
            return None
        rows = [
            row for row in self._critical_pair_rows()
            if row["state"] in {"candidate", "locked"}
            and float(row["critical_pair_score"]) >= self.critical_pair_exit_threshold
        ][: self.critical_pair_frontier_max_pairs]
        if not rows:
            return None
        cadence = max(1, round(1 / self.critical_pair_revisit_fraction))
        if iteration % cadence != cadence - 1:
            return None
        row = min(
            rows,
            key=lambda item: (
                int(item.get("revisit_count", 0)),
                -float(item.get("critical_pair_score", 0.0)),
                int(item.get("last_seen", 0)),
                item["source"],
                item["target"],
            ),
        )
        return (
            str(row["source"]),
            str(row["target"]),
            float(row["critical_pair_score"]),
            str(row["state"]),
        )

    def _endpoint_pair_counts(self) -> dict[str, float]:
        counts: dict[str, float] = defaultdict(float)
        for (src, tgt), count in self._local_conflict_pair_counts.items():
            explicit = self._explicit_conflict_pair_counts.get((src, tgt), 0)
            reasons = self._local_conflict_pair_reasons.get((src, tgt), [])
            semantic = self._semantic_conflict_strength(reasons)
            weight = count + 0.75 * explicit + semantic
            counts[src] += weight
            counts[tgt] += weight
        return counts

    def _relation_node_raw_scores(self) -> dict[str, float]:
        endpoint_counts = self._endpoint_pair_counts()
        scores: dict[str, float] = {}
        for cid, ns in self._node_stats.items():
            score = 0.0
            score += 1.10 * self._repair_entry_counts.get(cid, 0)
            score += 0.90 * self._local_subgraph_counts.get(cid, 0)
            score += 0.85 * endpoint_counts.get(cid, 0.0)
            score += 0.70 * self._amaf_node_evidence.get(cid, 0.0)
            score += 0.75 * self._path_fragment_evidence.get(cid, 0.0)
            score += 0.60 * ns.conflict_count
            if cid in self._detected_clauses:
                score += 2.0
            scores[cid] = score
        return scores

    def _relation_node_prior(self, cid: str) -> float:
        if not self.relation_first_enabled:
            return 0.0
        raw = self._relation_node_raw_scores()
        max_score = max(raw.values()) if raw else 0.0
        if max_score <= 1e-12:
            return 0.0
        return raw.get(cid, 0.0) / max_score

    def _relation_edge_raw_score(self, edge: tuple[str, str]) -> float:
        source, target = edge
        pair = self._pair_key(source, target)
        pair_count = self._local_conflict_pair_counts.get(pair, 0)
        explicit = self._explicit_conflict_pair_counts.get(pair, 0)
        semantic = self._semantic_conflict_strength(
            self._local_conflict_pair_reasons.get(pair, [])
        )
        critical = 0.0
        if pair in self._critical_pair_ledger:
            critical = self._critical_pair_score(self._critical_pair_ledger[pair])
        amaf = self._amaf_edge_evidence.get(edge, 0.0)
        reverse_amaf = self._amaf_edge_evidence.get((target, source), 0.0) * 0.55
        es = self._edge_stats.get(edge)
        conflict = es.avg_conflict if es and es.visit_count else 0.0
        return (
            1.55 * critical
            + 1.35 * semantic
            + 0.90 * explicit
            + 0.70 * pair_count
            + 0.65 * amaf
            + 0.35 * reverse_amaf
            + 0.55 * conflict
        )

    def _relation_edge_prior(
        self,
        edge: tuple[str, str],
        window_set: set[str] | None = None,
    ) -> float:
        if not self.relation_first_enabled:
            return 0.0
        raw_values = [
            self._relation_edge_raw_score((e.source, e.target))
            for e in self._internal_edges
        ]
        raw_values.extend(self._relation_edge_raw_score((b, a)) for a, b in self._edges_set)
        max_score = max(raw_values) if raw_values else 0.0
        if max_score <= 1e-12:
            return 0.0
        base = self._relation_edge_raw_score(edge) / max_score
        if window_set:
            source, target = edge
            frontier_node = target if source in window_set else source
            frontier_bonus = 0.25 * self._relation_node_prior(frontier_node)
            base = min(1.0, base + frontier_bonus)
        return base

    def _select_relation_probe_window(self, iteration: int) -> list[str] | None:
        if not self.relation_first_enabled:
            return None
        if iteration < self.relation_probe_min_rollouts:
            return None
        if self.relation_probe_fraction <= 0:
            return None
        cadence = max(1, round(1 / self.relation_probe_fraction))
        if iteration % cadence != cadence - 1:
            return None

        critical_pair = self._best_critical_pair_for_revisit(iteration)
        if critical_pair:
            source, target, score, state = critical_pair
            window = self._build_relation_probe_window(source, target)
            if len(window) >= 2:
                meta = {
                    "mode": "critical_pair_revisit",
                    "source": source,
                    "target": target,
                    "critical_pair_score": score,
                    "critical_pair_state": state,
                    "window": list(window),
                }
                self._last_selection_meta = meta
                self._selection_events.append({"iteration": iteration + 1, **meta})
                self._relation_probe_history.append({"iteration": iteration + 1, **meta})
                self._critical_revisit_history.append({"iteration": iteration + 1, **meta})
                if len(self._relation_probe_history) > self.relation_probe_max_history:
                    self._relation_probe_history = self._relation_probe_history[-self.relation_probe_max_history:]
                return window

        pair = self._best_relation_pair()
        if not pair:
            return None
        source, target, score = pair
        if score < self.relation_probe_min_score:
            return None

        window = self._build_relation_probe_window(source, target)
        if len(window) < 2:
            return None

        meta = {
            "mode": "relation_probe",
            "source": source,
            "target": target,
            "relation_score": score,
            "window": list(window),
        }
        self._last_selection_meta = meta
        self._selection_events.append({"iteration": iteration + 1, **meta})
        self._relation_probe_history.append({"iteration": iteration + 1, **meta})
        if len(self._relation_probe_history) > self.relation_probe_max_history:
            self._relation_probe_history = self._relation_probe_history[-self.relation_probe_max_history:]
        return window

    def _best_relation_pair(self) -> tuple[str, str, float] | None:
        candidates: dict[tuple[str, str], float] = defaultdict(float)
        for pair, count in self._local_conflict_pair_counts.items():
            reasons = self._local_conflict_pair_reasons.get(pair, [])
            semantic = self._semantic_conflict_strength(reasons)
            explicit = self._explicit_conflict_pair_counts.get(pair, 0)
            candidates[pair] += count + 0.8 * explicit + 1.5 * semantic

        for (src, tgt), value in self._amaf_edge_evidence.items():
            if src == tgt:
                continue
            candidates[self._pair_key(src, tgt)] += 0.45 * value

        node_scores = self._relation_node_raw_scores()
        ordered_nodes = [
            cid for cid, score in sorted(
                node_scores.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if score > 0
        ][:8]
        for idx, src in enumerate(ordered_nodes):
            for tgt in ordered_nodes[idx + 1:]:
                if self._are_graph_connected(src, tgt):
                    candidates[self._pair_key(src, tgt)] += (
                        0.20 * node_scores[src] + 0.20 * node_scores[tgt]
                    )

        if not candidates:
            return None
        pair, score = max(
            candidates.items(),
            key=lambda item: (item[1], item[0][0], item[0][1]),
        )
        return pair[0], pair[1], score

    def _are_graph_connected(self, source: str, target: str) -> bool:
        return (
            (source, target) in self._edges_set
            or (target, source) in self._edges_set
            or bool(self._shortest_undirected_path(source, target, max_hops=2))
        )

    def _shortest_undirected_path(
        self,
        source: str,
        target: str,
        max_hops: int,
    ) -> list[str]:
        if source == target:
            return [source]
        neighbors = {
            cid: set(self._adjacency.get(cid, [])) | set(self._reverse_adj.get(cid, []))
            for cid in self._scc_ids
        }
        queue: deque[tuple[str, list[str]]] = deque([(source, [source])])
        visited = {source}
        while queue:
            node, path = queue.popleft()
            if len(path) - 1 >= max_hops:
                continue
            for nxt in sorted(neighbors.get(node, [])):
                if nxt in visited:
                    continue
                next_path = path + [nxt]
                if nxt == target:
                    return next_path
                visited.add(nxt)
                queue.append((nxt, next_path))
        return []

    def _build_relation_probe_window(self, source: str, target: str) -> list[str]:
        path = self._shortest_undirected_path(
            source,
            target,
            max_hops=max(1, self.window_size - 1),
        )
        window: list[str] = path if path else [source, target]
        seen = set(window)

        def add_node(cid: str) -> None:
            if cid in seen or cid not in self._node_stats:
                return
            if len(window) >= self.window_size:
                return
            seen.add(cid)
            window.append(cid)

        frontier = list(window)
        neighbor_candidates: list[tuple[float, str]] = []
        for node in frontier:
            for neighbor in set(self._adjacency.get(node, [])) | set(self._reverse_adj.get(node, [])):
                if neighbor not in seen:
                    edge_prior = max(
                        self._relation_edge_prior((node, neighbor), set(window)),
                        self._relation_edge_prior((neighbor, node), set(window)),
                    )
                    node_prior = self._relation_node_prior(neighbor)
                    neighbor_candidates.append((edge_prior + node_prior, neighbor))

        for _score, cid in sorted(neighbor_candidates, key=lambda item: (-item[0], item[1])):
            add_node(cid)
            if len(window) >= self.window_size:
                break

        if len(window) < self.window_size:
            for cid, _score in sorted(
                self._relation_node_raw_scores().items(),
                key=lambda item: (-item[1], item[0]),
            ):
                add_node(cid)
                if len(window) >= self.window_size:
                    break

        return window[: self.window_size]

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

    @staticmethod
    def _extract_node_id(item: Any) -> str | None:
        if isinstance(item, str):
            return item
        if not isinstance(item, dict):
            return None
        for key in ("clause_id", "node_id", "id", "source", "target", "clause_a", "clause_b"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _normalize_window_nodes(self, raw_nodes: Any, window: list[str]) -> list[str]:
        if raw_nodes is None:
            return []
        if isinstance(raw_nodes, dict):
            raw_nodes = (
                raw_nodes.get("nodes")
                or raw_nodes.get("node_ids")
                or raw_nodes.get("clause_ids")
                or []
            )
        if isinstance(raw_nodes, str):
            raw_nodes = [piece.strip() for piece in raw_nodes.replace(";", ",").split(",")]
        if not isinstance(raw_nodes, list):
            return []

        window_set = set(window)
        seen: set[str] = set()
        nodes: list[str] = []
        for item in raw_nodes:
            cid = self._extract_node_id(item)
            if not cid or cid not in window_set or cid in seen:
                continue
            seen.add(cid)
            nodes.append(cid)
        return nodes

    def _normalize_window_edges(self, raw_edges: Any, window: list[str]) -> list[dict[str, Any]]:
        if raw_edges is None:
            return []
        if isinstance(raw_edges, dict):
            raw_edges = raw_edges.get("edges") or raw_edges.get("conflicts") or []
        if not isinstance(raw_edges, list):
            return []

        window_set = set(window)
        edges: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in raw_edges:
            if not isinstance(item, dict):
                continue
            source = item.get("source") or item.get("clause_a") or item.get("from")
            target = item.get("target") or item.get("clause_b") or item.get("to")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            if source not in window_set or target not in window_set or source == target:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            normalized = {
                "source": source,
                "target": target,
                "reason": str(item.get("reason") or item.get("description") or "")[:300],
            }
            for score_key in (
                "same_path_score",
                "mutual_incompatibility_score",
                "incompatibility_score",
                "severity_score",
                "no_fallback_score",
            ):
                if score_key in item:
                    normalized[score_key] = self._safe_float(item.get(score_key))
            if "no_fallback" in item:
                normalized["no_fallback"] = bool(item.get("no_fallback"))
            edges.append(normalized)
        return edges

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

        local_risk_subgraph_nodes = self._normalize_window_nodes(
            resp.get("local_risk_subgraph_nodes")
            or resp.get("risk_subgraph_nodes")
            or resp.get("local_risk_subgraph"),
            window,
        )
        repair_entry_nodes = self._normalize_window_nodes(
            resp.get("repair_entry_nodes")
            or resp.get("repair_nodes")
            or resp.get("repair_entries"),
            window,
        )
        local_conflict_edges = self._normalize_window_edges(
            resp.get("local_conflict_edges")
            or resp.get("risk_subgraph_edges")
            or conflicts,
            window,
        )
        critical_pair_edges = self._normalize_window_edges(
            resp.get("critical_pairs")
            or resp.get("critical_pair_edges")
            or resp.get("critical_relations"),
            window,
        )
        if critical_pair_edges:
            by_pair = {
                (edge["source"], edge["target"]): edge
                for edge in local_conflict_edges
            }
            for edge in critical_pair_edges:
                edge["critical_pair"] = True
                key = (edge["source"], edge["target"])
                if key in by_pair:
                    existing = by_pair[key]
                    if edge.get("reason") and edge["reason"] not in existing.get("reason", ""):
                        existing["reason"] = (
                            f"{existing.get('reason', '')}; critical_pair: {edge['reason']}"
                        )[:300]
                    for score_key in (
                        "same_path_score",
                        "mutual_incompatibility_score",
                        "incompatibility_score",
                        "severity_score",
                        "no_fallback_score",
                        "no_fallback",
                        "critical_pair",
                    ):
                        if score_key in edge:
                            existing[score_key] = edge[score_key]
                else:
                    local_conflict_edges.append(edge)
                    by_pair[key] = edge
        if not local_risk_subgraph_nodes:
            inferred = set(repair_entry_nodes)
            for edge in local_conflict_edges:
                inferred.add(edge["source"])
                inferred.add(edge["target"])
            local_risk_subgraph_nodes = [cid for cid in window if cid in inferred]

        entry = TranspositionEntry(
            clause_ids=sorted(window),
            clause_evaluations=evaluations,
            clause_reasonings=reasonings,
            conflicts=conflicts,
            local_risk_subgraph_nodes=local_risk_subgraph_nodes,
            local_conflict_edges=local_conflict_edges,
            repair_entry_nodes=repair_entry_nodes,
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
            "clause pairs. If two clauses form a severe same-path incompatibility "
            "that has no obvious fallback or repair-free interpretation, also list "
            "that pair under critical_pairs. Do not invent a critical pair unless "
            "both endpoints and the relation are visible in this window.\n\n"
            "Output STRICTLY as JSON:\n"
            "{\n"
            '"clause_evaluations": {\n'
            + ",\n".join(
                f'  "{cid}": {{"risk_score": 0.0, "reasoning": "brief"}}'
                for cid in window
            )
            + '\n},\n'
            '"local_risk_subgraph_nodes": ["id"],\n'
            '"local_conflict_edges": [\n'
            '  {"source": "id", "target": "id", "reason": "..."}\n'
            "],\n"
            '"critical_pairs": [\n'
            '  {"source": "id", "target": "id", "reason": "same-path severe incompatibility", '
            '"same_path_score": 0.0, "mutual_incompatibility_score": 0.0, '
            '"severity_score": 0.0, "no_fallback": false}\n'
            "],\n"
            '"repair_entry_nodes": ["id"],\n'
            '"conflicts": [\n'
            '  {"clause_a": "id", "clause_b": "id", "description": "..."}\n'
            "]\n"
            "}"
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
        counted_local_pairs: set[tuple[str, str]] = set()
        critical_updates: dict[tuple[str, str], dict[str, Any]] = {}

        def queue_critical_update(
            source: str,
            target: str,
            reason: str,
            *,
            explicit: bool = False,
            local: bool = False,
            edge_features: dict[str, Any] | None = None,
        ) -> None:
            if source not in self._node_stats or target not in self._node_stats or source == target:
                return
            key = self._pair_key(source, target)
            update = critical_updates.setdefault(
                key,
                {
                    "source": key[0],
                    "target": key[1],
                    "reasons": [],
                    "explicit_count": 0,
                    "local_count": 0,
                    "edge_features": {},
                },
            )
            if reason and reason not in update["reasons"]:
                update["reasons"].append(reason)
            if explicit:
                update["explicit_count"] += 1
            if local:
                update["local_count"] += 1
            for feature_key, feature_value in (edge_features or {}).items():
                if feature_key == "no_fallback":
                    update["edge_features"][feature_key] = (
                        bool(feature_value)
                        or bool(update["edge_features"].get(feature_key))
                    )
                    continue
                update["edge_features"][feature_key] = max(
                    self._safe_float(update["edge_features"].get(feature_key)),
                    self._safe_float(feature_value),
                )

        for conf in entry.conflicts:
            if isinstance(conf, dict):
                a = conf.get("clause_a", "")
                b = conf.get("clause_b", "")
                desc = str(conf.get("description") or "")[:300]
                semantic_gain = self._semantic_conflict_strength([desc])
                if a in self._node_stats:
                    self._node_stats[a].conflict_count += 1
                    conflict_nodes.add(a)
                    self._amaf_node_evidence[a] += 1.0 + semantic_gain
                if b in self._node_stats:
                    self._node_stats[b].conflict_count += 1
                    conflict_nodes.add(b)
                    self._amaf_node_evidence[b] += 1.0 + semantic_gain
                if a in self._node_stats and b in self._node_stats and a != b:
                    key = tuple(sorted((a, b)))
                    if key not in counted_local_pairs:
                        self._local_conflict_pair_counts[key] += 1
                        counted_local_pairs.add(key)
                    self._explicit_conflict_pair_counts[key] += 1
                    if desc and len(self._local_conflict_pair_reasons[key]) < 3:
                        self._local_conflict_pair_reasons[key].append(desc)
                    self._amaf_edge_evidence[(a, b)] += 1.0 + semantic_gain
                    self._amaf_edge_evidence[(b, a)] += 0.45 + 0.5 * semantic_gain
                    queue_critical_update(a, b, desc, explicit=True)

        for cid in entry.local_risk_subgraph_nodes:
            if cid in self._node_stats:
                self._local_subgraph_counts[cid] += 1
                self._amaf_node_evidence[cid] += 0.65
                self._path_fragment_evidence[cid] += 0.45
        for cid in entry.repair_entry_nodes:
            if cid in self._node_stats:
                self._repair_entry_counts[cid] += 1
                self._amaf_node_evidence[cid] += 0.90
                self._path_fragment_evidence[cid] += 0.70
        for edge in entry.local_conflict_edges:
            source = edge.get("source")
            target = edge.get("target")
            if source in self._node_stats and target in self._node_stats and source != target:
                key = tuple(sorted((source, target)))
                if key not in counted_local_pairs:
                    self._local_conflict_pair_counts[key] += 1
                    counted_local_pairs.add(key)
                reason = str(edge.get("reason") or "")[:300]
                if reason and len(self._local_conflict_pair_reasons[key]) < 3:
                    self._local_conflict_pair_reasons[key].append(reason)
                semantic_gain = self._semantic_conflict_strength([reason])
                self._amaf_node_evidence[source] += 0.75 + semantic_gain
                self._amaf_node_evidence[target] += 0.75 + semantic_gain
                self._amaf_edge_evidence[(source, target)] += 1.0 + semantic_gain
                self._amaf_edge_evidence[(target, source)] += 0.35 + 0.5 * semantic_gain
                self._path_fragment_evidence[source] += 0.35
                self._path_fragment_evidence[target] += 0.35
                queue_critical_update(
                    source,
                    target,
                    reason,
                    local=True,
                    edge_features=edge,
                )

        rollout_index = len(self._trace_events) + 1
        for update in critical_updates.values():
            self._update_critical_pair_ledger(
                update["source"],
                update["target"],
                update["reasons"],
                explicit_count=update["explicit_count"],
                local_count=update["local_count"],
                window=window,
                iteration=rollout_index,
                edge_features=update["edge_features"],
            )

        high_context_nodes = (
            set(entry.local_risk_subgraph_nodes)
            | set(entry.repair_entry_nodes)
            | conflict_nodes
        )
        for i in range(len(window) - 1):
            src = window[i]
            tgt = window[i + 1]
            if src in high_context_nodes or tgt in high_context_nodes:
                self._amaf_edge_evidence[(src, tgt)] += 0.25
                self._amaf_edge_evidence[(tgt, src)] += 0.15
                self._path_fragment_evidence[src] += 0.15
                self._path_fragment_evidence[tgt] += 0.15

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

    # ── Trace ───────────────────────────────────────────────────────

    def _record_trace(
        self,
        iteration: int,
        window: list[str],
        entry: TranspositionEntry,
        is_tt_hit: bool,
    ) -> None:
        """Record one completed rollout for convergence/anytime analysis."""
        if not self.trace_enabled:
            return

        top_risk = sorted(
            (
                (cid, ns.avg_risk, ns.visit_count)
                for cid, ns in self._node_stats.items()
                if ns.visit_count > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )[:8]
        relation_raw = self._relation_node_raw_scores()
        top_relation = sorted(
            (
                (cid, score, self._relation_node_prior(cid))
                for cid, score in relation_raw.items()
                if score > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )[:8]
        event = {
            "completion_index": len(self._trace_events) + 1,
            "iteration": iteration + 1,
            "window": list(window),
            "is_tt_hit": bool(is_tt_hit),
            "selection": dict(self._last_selection_meta),
            "scores": dict(entry.clause_evaluations),
            "local_risk_subgraph_nodes": list(entry.local_risk_subgraph_nodes),
            "repair_entry_nodes": list(entry.repair_entry_nodes),
            "local_conflict_edges": list(entry.local_conflict_edges),
            "conflicts": list(entry.conflicts),
            "oc_detected_so_far": sorted(self._detected_clauses),
            "top_risk_so_far": [
                {"clause_id": cid, "avg_risk": score, "visit_count": visits}
                for cid, score, visits in top_risk
            ],
            "top_relation_evidence_so_far": [
                {"clause_id": cid, "raw_evidence": score, "prior": prior}
                for cid, score, prior in top_relation
            ],
            "top_critical_pairs_so_far": self._critical_pair_rows()[:8],
        }
        self._trace_events.append(event)

    # ── Result Building ─────────────────────────────────────────────

    @staticmethod
    def _median(values: list[float]) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    @staticmethod
    def _semantic_conflict_strength(reasons: list[str]) -> float:
        """Estimate whether a reported pair is a concrete incompatibility.

        This deliberately uses domain-agnostic wording so the evidence memory
        does not learn experiment-specific labels.
        """
        text = " ".join(reasons).lower()
        if not text:
            return 0.0

        score = 0.0
        strong_terms = (
            "incompatible",
            "incompatibility",
            "mutually exclusive",
            "cannot both",
            "contradict",
            "contradiction",
            "violates",
            "violate",
            "opposite",
        )
        medium_terms = (
            "conflict",
            "conflicting",
            "inconsistent",
            "inconsistency",
            "mismatch",
            "invalid",
            "unreconciled",
            "not reconciled",
        )
        weak_terms = (
            "ambiguous",
            "ambiguity",
            "unclear",
            "underspecified",
            "overlap",
            "overlapping",
            "circular",
            "redundant",
            "redundancy",
        )
        if any(term in text for term in strong_terms):
            score = max(score, 1.0)
        if any(term in text for term in medium_terms):
            score = max(score, 0.65)
        if any(term in text for term in weak_terms):
            score = max(score, 0.35)
        if score >= 0.35 and ("%" in text or "percent" in text or any(ch.isdigit() for ch in text)):
            score = min(1.0, score + 0.1)
        return score

    def _normalize_component(
        self,
        values: dict[str, float | int],
    ) -> dict[str, float]:
        clean = {
            cid: max(0.0, float(values.get(cid, 0.0)))
            for cid in self._scc_ids
        }
        max_value = max(clean.values()) if clean else 0.0
        if max_value <= 1e-12:
            return {}
        return {
            cid: value / max_value
            for cid, value in clean.items()
            if value > 0
        }

    def _select_dynamic_core_subgraph(
        self,
        context_selected: set[str],
        evidence_scores: dict[str, dict[str, Any]],
        conflict_probability_matrix: list[dict[str, Any]],
        cap: int,
        index: dict[str, int],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Select a dynamically maintained core from evidence-bearing nodes.

        The wider context subgraph is still useful for explanation, but the
        core subgraph should stop when additional nodes no longer add enough
        evidence. This lets later rollouts replace weak early hypotheses
        instead of always filling the maximum budget.
        """
        if not context_selected:
            return [], []

        pair_endpoint_scores: dict[str, float] = defaultdict(float)
        pair_endpoint_counts: dict[str, int] = defaultdict(int)
        strong_edges: list[dict[str, Any]] = []
        protected_edge_candidates: list[dict[str, Any]] = []
        protected_edges: list[dict[str, Any]] = []
        protected_nodes: set[str] = set()
        for edge in conflict_probability_matrix:
            source = edge.get("source")
            target = edge.get("target")
            if source not in index or target not in index:
                continue
            pair_score = float(edge.get("pair_score", 0.0))
            semantic_strength = float(edge.get("semantic_strength", 0.0))
            explicit_count = int(edge.get("explicit_count", 0))
            critical_score = float(edge.get("critical_pair_score", 0.0))
            critical_state = str(edge.get("critical_state", ""))
            critical_support = int(edge.get("critical_support_count", 0))
            is_protected_critical = (
                critical_state == "locked"
                or (
                    critical_score >= self.critical_pair_core_min_score
                    and critical_support >= self.critical_pair_lock_support
                )
            )
            is_evidence_edge = (
                pair_score >= self.evidence_pair_memory_min_score
                or semantic_strength >= 0.65
                or explicit_count > 0
                or is_protected_critical
            )
            if not is_evidence_edge:
                continue
            strong_edges.append(edge)
            if is_protected_critical:
                protected_edge_candidates.append(edge)
            for cid in (source, target):
                pair_endpoint_scores[cid] = max(pair_endpoint_scores[cid], pair_score)
                pair_endpoint_counts[cid] += 1

        if protected_edge_candidates:
            protected_edge_candidates.sort(
                key=lambda edge: (
                    -float(edge.get("critical_pair_score", 0.0)),
                    -float(edge.get("severity_strength", 0.0)),
                    -float(edge.get("same_path_strength", 0.0)),
                    -float(edge.get("no_fallback_strength", 0.0)),
                    -int(edge.get("critical_support_count", 0)),
                    -int(edge.get("critical_revisit_count", 0)),
                    str(edge.get("source")),
                    str(edge.get("target")),
                )
            )
            max_protected_edges = len(protected_edge_candidates)
            if self.critical_pair_core_max_edge_ratio is not None:
                max_protected_edges = min(
                    max_protected_edges,
                    max(1, math.ceil(cap * self.critical_pair_core_max_edge_ratio)),
                )
            if self.critical_pair_core_max_edges > 0:
                max_protected_edges = min(
                    max_protected_edges,
                    self.critical_pair_core_max_edges,
                )
            protected_edges = protected_edge_candidates[:max_protected_edges]
            for edge in protected_edges:
                protected_nodes.update({str(edge.get("source")), str(edge.get("target"))})

        priority_rows: list[dict[str, Any]] = []
        for cid in context_selected:
            info = evidence_scores.get(cid, {})
            score = float(info.get("score", 0.0))
            pair_score = float(pair_endpoint_scores.get(cid, 0.0))
            oc_bonus = 0.16 if cid in self._detected_clauses else 0.0
            priority = score + 0.24 * pair_score + oc_bonus
            if priority <= 0:
                continue
            priority_rows.append({
                "clause_id": cid,
                "priority": priority,
                "evidence_score": score,
                "pair_score": pair_score,
                "pair_endpoint_count": pair_endpoint_counts.get(cid, 0),
                "support_count": int(info.get("support_count", 0)),
                "oc": cid in self._detected_clauses,
            })

        priority_rows.sort(
            key=lambda row: (
                -row["priority"],
                -row["support_count"],
                -row["pair_endpoint_count"],
                index[row["clause_id"]],
            )
        )
        if not priority_rows:
            fallback = sorted(context_selected, key=lambda cid: index.get(cid, len(index)))[:1]
            return fallback, []

        top_priority = max(priority_rows[0]["priority"], 1e-9)
        core_min_nodes = min(cap, max(1, self.evidence_core_min_nodes))
        selected: set[str] = set()
        stop_reason = "exhausted_candidates"
        prev_priority = priority_rows[0]["priority"]

        # Seed with a very small number of the strongest relation edges. This
        # keeps relation-first evidence from being reduced to single-node rank,
        # while preventing every moderately suspicious edge endpoint from
        # filling the core to the hard cap.
        if protected_edges:
            protected_edges.sort(
                key=lambda edge: (
                    -float(edge.get("critical_pair_score", 0.0)),
                    -float(edge.get("semantic_strength", 0.0)),
                    -int(edge.get("critical_support_count", 0)),
                    str(edge.get("source")),
                    str(edge.get("target")),
                )
            )
            for edge in protected_edges:
                endpoints = [
                    cid for cid in (edge.get("source"), edge.get("target"))
                    if isinstance(cid, str) and cid in context_selected
                ]
                if len(endpoints) < 2:
                    continue
                if len(selected.union(endpoints)) > cap:
                    continue
                selected.update(endpoints)

        if strong_edges:
            top_pair_score = max(float(edge.get("pair_score", 0.0)) for edge in strong_edges)
            relation_seed_node_cap = min(cap, core_min_nodes)
            relation_seed_min_score = max(
                self.evidence_pair_memory_min_score,
                top_pair_score * 0.90,
            )
            for edge in strong_edges:
                if len(selected) >= relation_seed_node_cap:
                    break
                pair_score = float(edge.get("pair_score", 0.0))
                semantic_strength = float(edge.get("semantic_strength", 0.0))
                if pair_score < relation_seed_min_score and semantic_strength < 0.9:
                    continue
                endpoints = [
                    cid for cid in (edge.get("source"), edge.get("target"))
                    if isinstance(cid, str) and cid in context_selected
                ]
                if len(endpoints) < 2:
                    continue
                if len(selected.union(endpoints)) > relation_seed_node_cap:
                    continue
                selected.update(endpoints)

        for row_index, row in enumerate(priority_rows):
            if len(selected) >= cap:
                stop_reason = "hit_cap"
                break

            cid = row["clause_id"]
            priority = float(row["priority"])
            relative = priority / top_priority
            gap = max(0.0, (prev_priority - priority) / top_priority)
            if cid in selected:
                priority_rows[row_index]["selected"] = True
                priority_rows[row_index]["relative_priority"] = relative
                prev_priority = priority
                continue

            must_keep = row["oc"]
            if cid in protected_nodes:
                must_keep = True

            if len(selected) >= core_min_nodes and not must_keep:
                if priority < self.evidence_core_min_score:
                    stop_reason = "below_absolute_score"
                    break
                if gap >= self.evidence_core_stop_gap:
                    stop_reason = "score_gap"
                    break
                if relative < self.evidence_core_tail_relative_score:
                    stop_reason = "below_tail_relative_score"
                    break
                if relative < self.evidence_core_min_relative_score:
                    stop_reason = "below_relative_score"
                    break

            selected.add(cid)
            priority_rows[row_index]["selected"] = True
            priority_rows[row_index]["relative_priority"] = relative
            prev_priority = priority

        # Pair closure can still revise the core: if a high-confidence relation
        # touches the current core, keep its counterpart even when that
        # counterpart is not individually high-risk.
        closure_top_pair_score = max(
            [float(edge.get("pair_score", 0.0)) for edge in strong_edges] or [0.0]
        )
        for edge in strong_edges:
            if len(selected) >= cap:
                break
            source = edge["source"]
            target = edge["target"]
            if source not in context_selected or target not in context_selected:
                continue
            if (source in selected) == (target in selected):
                continue
            counterpart = target if source in selected else source
            pair_score = float(edge.get("pair_score", 0.0))
            semantic_strength = float(edge.get("semantic_strength", 0.0))
            counterpart_priority = next(
                (
                    float(row["priority"])
                    for row in priority_rows
                    if row["clause_id"] == counterpart
                ),
                0.0,
            )
            if (
                pair_score >= max(
                    self.evidence_pair_closure_min_score,
                    closure_top_pair_score * 0.90,
                )
                and (
                    edge.get("critical_state") == "locked"
                    or float(edge.get("critical_pair_score", 0.0)) >= self.critical_pair_core_min_score
                    or semantic_strength >= 0.9
                    or counterpart_priority / top_priority >= 0.35
                )
            ):
                selected.add(counterpart)

        ordered_core = [cid for cid in self._scc_ids if cid in selected]
        for row in priority_rows:
            row.setdefault("selected", row["clause_id"] in selected)
            row.setdefault("relative_priority", row["priority"] / top_priority)
        priority_rows.insert(0, {
            "policy": "dynamic_core_subgraph",
            "stop_reason": stop_reason,
            "cap": cap,
            "core_size": len(ordered_core),
            "context_size": len(context_selected),
            "hit_cap": len(ordered_core) >= cap,
            "min_relative_score": self.evidence_core_min_relative_score,
            "tail_relative_score": self.evidence_core_tail_relative_score,
            "stop_gap": self.evidence_core_stop_gap,
            "protected_critical_edge_candidates": len(protected_edge_candidates),
            "protected_critical_edge_cap_ratio": self.critical_pair_core_max_edge_ratio,
            "protected_critical_edge_cap": len(protected_edges),
            "protected_critical_nodes": [
                cid for cid in self._scc_ids if cid in protected_nodes
            ],
            "protected_critical_edges": [
                {
                    "source": edge.get("source"),
                    "target": edge.get("target"),
                    "critical_pair_score": edge.get("critical_pair_score"),
                    "critical_state": edge.get("critical_state"),
                }
                for edge in protected_edges
            ],
        })
        return ordered_core, priority_rows

    def _build_evidence_summary(
        self,
        local_pair_edges: list[dict[str, Any]],
        endpoint_counts: dict[str, int],
    ) -> dict[str, Any]:
        """Aggregate rollout evidence into a blind risk subgraph.

        This is the implementation-side counterpart of the paper/demo's
        Conflict Probability Matrix: local rollout evidence is accumulated
        across transposition entries, normalized per SCC, and compressed into
        a small candidate subgraph without using ground-truth labels.
        """
        n = len(self._scc_ids)
        index = {cid: i for i, cid in enumerate(self._scc_ids)}
        critical_pair_rows = self._critical_pair_rows()
        critical_pair_endpoint_scores: dict[str, float] = defaultdict(float)
        for row in critical_pair_rows:
            score = float(row.get("critical_pair_score", 0.0))
            if score < self.critical_pair_exit_threshold:
                continue
            state_bonus = 1.25 if row.get("state") == "locked" else 1.0
            for cid in (row.get("source"), row.get("target")):
                if isinstance(cid, str) and cid in index:
                    critical_pair_endpoint_scores[cid] += score * state_bonus

        risk_values = [
            ns.avg_risk
            for ns in self._node_stats.values()
            if ns.visit_count > 0
        ]
        risk_baseline = self._median(risk_values)
        raw_components: dict[str, dict[str, float | int]] = {
            "risk_surplus": {
                cid: max(0.0, ns.avg_risk - risk_baseline)
                for cid, ns in self._node_stats.items()
                if ns.visit_count > 0
            },
            "conflict_rate": {
                cid: ns.conflict_count / max(1, ns.visit_count)
                for cid, ns in self._node_stats.items()
                if ns.conflict_count > 0
            },
            "local_risk_subgraph": dict(self._local_subgraph_counts),
            "repair_entry": dict(self._repair_entry_counts),
            "conflict_endpoint": dict(endpoint_counts),
            "oc_signal": {cid: 1.0 for cid in self._detected_clauses},
            "amaf_node_evidence": dict(self._amaf_node_evidence),
            "path_fragment_evidence": dict(self._path_fragment_evidence),
            "relation_evidence_prior": self._relation_node_raw_scores(),
            "critical_pair_endpoint": critical_pair_endpoint_scores,
        }

        normalized_components = {
            name: normalized
            for name, values in raw_components.items()
            if (normalized := self._normalize_component(values))
        }

        evidence_scores: dict[str, dict[str, Any]] = {}
        component_names = list(normalized_components)
        for cid in self._scc_ids:
            parts = {
                name: normalized_components[name].get(cid, 0.0)
                for name in component_names
            }
            active_parts = {
                name: value
                for name, value in parts.items()
                if value > 0
            }
            score = (
                sum(parts.values()) / len(component_names)
                if component_names else 0.0
            )
            evidence_scores[cid] = {
                "score": score,
                "support_count": len(active_parts),
                "components": active_parts,
                "raw": {
                    name: raw_components[name].get(cid, 0)
                    for name in raw_components
                    if raw_components[name].get(cid, 0)
                },
            }

        ranking_by_evidence = sorted(
            (
                (cid, info["score"])
                for cid, info in evidence_scores.items()
                if info["score"] > 0
            ),
            key=lambda item: (-item[1], -evidence_scores[item[0]]["support_count"], index[item[0]]),
        )

        max_pair_count = max(
            [int(edge.get("count", 0)) for edge in local_pair_edges] or [0]
        )
        max_explicit_count = max(
            [int(edge.get("explicit_count", 0)) for edge in local_pair_edges] or [0]
        )
        conflict_probability_matrix = []
        edge_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
        for edge in local_pair_edges:
            count = int(edge.get("count", 0))
            explicit_count = int(edge.get("explicit_count", 0))
            source = edge.get("source")
            target = edge.get("target")
            if not isinstance(source, str) or not isinstance(target, str) or count <= 0:
                continue
            reasons = edge.get("reasons", [])
            semantic_strength = self._semantic_conflict_strength(reasons)
            count_score = math.log1p(count) / math.log1p(max(1, max_pair_count))
            explicit_score = (
                math.log1p(explicit_count) / math.log1p(max_explicit_count)
                if max_explicit_count > 0 and explicit_count > 0 else 0.0
            )
            endpoint_score = (
                evidence_scores.get(source, {}).get("score", 0.0)
                + evidence_scores.get(target, {}).get("score", 0.0)
            ) / 2
            pair_score = (
                0.45 * semantic_strength
                + 0.20 * explicit_score
                + 0.20 * count_score
                + 0.15 * endpoint_score
            )
            matrix_edge = {
                "source": source,
                "target": target,
                "count": count,
                "explicit_count": explicit_count,
                "probability_proxy": count / max(1, max_pair_count),
                "semantic_strength": semantic_strength,
                "pair_score": pair_score,
                "reasons": reasons,
            }
            conflict_probability_matrix.append(matrix_edge)
            edge_by_pair[self._pair_key(source, target)] = matrix_edge

        for row in critical_pair_rows:
            source = row.get("source")
            target = row.get("target")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            if source not in index or target not in index:
                continue
            critical_score = float(row.get("critical_pair_score", 0.0))
            if critical_score < self.critical_pair_exit_threshold:
                continue
            key = self._pair_key(source, target)
            reasons = list(row.get("reasons", []))
            if key in edge_by_pair:
                edge = edge_by_pair[key]
                edge["critical_pair_score"] = critical_score
                edge["critical_state"] = row.get("state", "observed")
                edge["critical_support_count"] = int(row.get("support_count", 0))
                edge["critical_revisit_count"] = int(row.get("revisit_count", 0))
                edge["severity_strength"] = float(row.get("severity_strength", 0.0))
                edge["same_path_strength"] = float(row.get("same_path_strength", 0.0))
                edge["no_fallback_strength"] = float(row.get("no_fallback_strength", 0.0))
                edge["pair_score"] = max(float(edge.get("pair_score", 0.0)), critical_score)
                edge["semantic_strength"] = max(
                    float(edge.get("semantic_strength", 0.0)),
                    float(row.get("semantic_strength", 0.0)),
                )
                existing_reasons = list(edge.get("reasons", []))
                for reason in reasons:
                    if reason not in existing_reasons and len(existing_reasons) < 5:
                        existing_reasons.append(reason)
                edge["reasons"] = existing_reasons
                continue
            matrix_edge = {
                "source": source,
                "target": target,
                "count": int(row.get("support_count", 0)),
                "explicit_count": int(row.get("explicit_count", 0)),
                "probability_proxy": 0.0,
                "semantic_strength": float(row.get("semantic_strength", 0.0)),
                "severity_strength": float(row.get("severity_strength", 0.0)),
                "same_path_strength": float(row.get("same_path_strength", 0.0)),
                "no_fallback_strength": float(row.get("no_fallback_strength", 0.0)),
                "critical_pair_score": critical_score,
                "critical_state": row.get("state", "observed"),
                "critical_support_count": int(row.get("support_count", 0)),
                "critical_revisit_count": int(row.get("revisit_count", 0)),
                "pair_score": critical_score,
                "reasons": reasons,
            }
            conflict_probability_matrix.append(matrix_edge)
            edge_by_pair[key] = matrix_edge
        conflict_probability_matrix.sort(
            key=lambda edge: (
                -edge["pair_score"],
                -edge["semantic_strength"],
                -edge["explicit_count"],
                -edge["count"],
                edge["source"],
                edge["target"],
            )
        )

        cap = min(
            n,
            max(
                self.evidence_subgraph_min_nodes,
                math.ceil(n * self.evidence_subgraph_max_ratio),
            ),
        )
        selected: set[str] = set()
        pair_memory_nodes: set[str] = set()
        pair_memory_node_scores: dict[str, float] = {}
        pair_memory_edges: list[dict[str, Any]] = []

        if self.relation_first_enabled:
            # Relation-first compression: preserve strong relation/path
            # evidence before falling back to single-node risk. A low-risk
            # node can enter the subgraph when previous rollouts prove that it
            # is an endpoint, repair entry, bridge, or path fragment.
            for edge in conflict_probability_matrix:
                if len(selected) >= cap:
                    break
                if (
                    edge["pair_score"] < self.evidence_pair_memory_min_score
                    and edge["semantic_strength"] < 0.65
                    and edge["explicit_count"] <= 0
                ):
                    continue
                endpoints = [
                    cid for cid in (edge["source"], edge["target"])
                    if cid in index
                ]
                if len(endpoints) < 2:
                    continue
                for cid in endpoints:
                    if len(selected) >= cap:
                        break
                    selected.add(cid)
                    pair_memory_nodes.add(cid)
                    pair_memory_node_scores[cid] = max(
                        pair_memory_node_scores.get(cid, 0.0),
                        float(edge["pair_score"]),
                    )
                pair_memory_edges.append(edge)

            relation_rank = sorted(
                evidence_scores.items(),
                key=lambda item: (
                    -item[1]["support_count"],
                    -item[1]["score"],
                    index[item[0]],
                ),
            )
            for cid, info in relation_rank:
                if len(selected) >= cap:
                    break
                if info["support_count"] < 2:
                    continue
                selected.add(cid)

        # OC nodes are statistically calibrated alarms; keep them as evidence
        # nodes, but relation-first mode no longer lets OC crowd out stronger
        # pair/path evidence discovered by search.
        for cid in sorted(self._detected_clauses, key=lambda node: index.get(node, n)):
            if cid in index and len(selected) < cap:
                selected.add(cid)

        pair_node_soft_cap = min(
            cap,
            max(2, math.ceil(cap * self.evidence_pair_memory_max_ratio)),
        )
        for edge in conflict_probability_matrix:
            if len(selected) >= cap:
                break
            if (
                edge["pair_score"] < self.evidence_pair_memory_min_score
                and edge["semantic_strength"] < 0.8
            ):
                continue
            endpoints = [
                cid for cid in (edge["source"], edge["target"])
                if cid in index
            ]
            if len(endpoints) < 2:
                continue
            new_nodes = [cid for cid in endpoints if cid not in selected]
            if not new_nodes:
                continue
            within_soft_cap = len(selected) + len(new_nodes) <= pair_node_soft_cap
            one_endpoint_already_selected = any(cid in selected for cid in endpoints)
            strong_pair = edge["semantic_strength"] >= 0.8
            if not (within_soft_cap or one_endpoint_already_selected or strong_pair):
                continue
            for cid in endpoints:
                if len(selected) >= cap:
                    break
                selected.add(cid)
                pair_memory_nodes.add(cid)
                pair_memory_node_scores[cid] = max(
                    pair_memory_node_scores.get(cid, 0.0),
                    float(edge["pair_score"]),
                )
            pair_memory_edges.append(edge)

        for cid, _score in ranking_by_evidence:
            if len(selected) >= cap:
                break
            selected.add(cid)

        # If a meaningful conflict pair touches the selected region, keep the
        # counterpart. When the cap is already full, replace the weakest
        # non-OC node; this preserves pair-level evidence rather than letting
        # repeated low-value noise evict one side of a concrete conflict.
        for edge in conflict_probability_matrix:
            source = edge["source"]
            target = edge["target"]
            if (
                edge["pair_score"] < self.evidence_pair_closure_min_score
                and edge["semantic_strength"] < 0.65
            ):
                continue
            if (source in selected) == (target in selected):
                continue
            counterpart = target if source in selected else source
            if counterpart not in index:
                continue
            if len(selected) < cap:
                selected.add(counterpart)
                pair_memory_nodes.add(counterpart)
                pair_memory_node_scores[counterpart] = max(
                    pair_memory_node_scores.get(counterpart, 0.0),
                    float(edge["pair_score"]),
                )
                pair_memory_edges.append(edge)
                continue

            replaceable = [
                cid for cid in selected
                if cid not in self._detected_clauses
                and cid not in {source, target}
            ]
            if not replaceable:
                continue
            weakest = min(
                replaceable,
                key=lambda cid: (
                    pair_memory_node_scores.get(cid, 0.0),
                    evidence_scores.get(cid, {}).get("score", 0.0),
                    evidence_scores.get(cid, {}).get("support_count", 0),
                    -index[cid],
                ),
            )
            weakest_pair_score = pair_memory_node_scores.get(weakest, 0.0)
            weakest_score = evidence_scores.get(weakest, {}).get("score", 0.0)
            if edge["pair_score"] >= max(
                self.evidence_pair_closure_min_score,
                weakest_pair_score * 1.05,
                weakest_score * 0.85,
            ):
                selected.remove(weakest)
                selected.add(counterpart)
                pair_memory_nodes.add(counterpart)
                pair_memory_node_scores[counterpart] = max(
                    pair_memory_node_scores.get(counterpart, 0.0),
                    float(edge["pair_score"]),
                )
                pair_memory_edges.append(edge)

        if not selected and self._scc_ids:
            fallback_node = max(
                self._node_stats.items(),
                key=lambda item: (item[1].avg_risk, -index[item[0]]),
            )[0]
            selected.add(fallback_node)

        legacy_context_selected = set(selected)
        core_candidate_universe = {
            cid
            for cid, info in evidence_scores.items()
            if cid in index
            and (
                float(info.get("score", 0.0)) > 0
                or int(info.get("support_count", 0)) > 0
            )
        }
        core_candidate_universe.update(
            cid for cid in self._detected_clauses if cid in index
        )
        for edge in conflict_probability_matrix:
            pair_score = float(edge.get("pair_score", 0.0))
            semantic_strength = float(edge.get("semantic_strength", 0.0))
            explicit_count = int(edge.get("explicit_count", 0))
            if (
                pair_score < self.evidence_pair_memory_min_score
                and semantic_strength < 0.65
                and explicit_count <= 0
            ):
                continue
            for cid in (edge.get("source"), edge.get("target")):
                if isinstance(cid, str) and cid in index:
                    core_candidate_universe.add(cid)
        if not core_candidate_universe:
            core_candidate_universe = set(legacy_context_selected)

        ordered_nodes, dynamic_core_rows = self._select_dynamic_core_subgraph(
            context_selected=core_candidate_universe,
            evidence_scores=evidence_scores,
            conflict_probability_matrix=conflict_probability_matrix,
            cap=cap,
            index=index,
        )
        context_selected = set(ordered_nodes)
        for cid in self._scc_ids:
            if len(context_selected) >= cap:
                break
            if cid in legacy_context_selected:
                context_selected.add(cid)
        for cid, _score in ranking_by_evidence:
            if len(context_selected) >= cap:
                break
            context_selected.add(cid)
        ordered_context_nodes = [
            cid for cid in self._scc_ids if cid in context_selected
        ]
        total = max(1, n)
        return {
            "evidence_node_scores": evidence_scores,
            "evidence_component_names": component_names,
            "evidence_component_policy": (
                "dynamic per-SCC normalization over risk surplus, conflict rate, "
                "LLM-declared local subgraphs, repair entries, conflict endpoints, "
                "OC signals, AMAF/RAVE-style node evidence, path-fragment "
                "evidence, and pair-level conflict memory"
            ),
            "ranking_by_evidence": ranking_by_evidence,
            "conflict_probability_matrix": conflict_probability_matrix,
            "evidence_pair_memory_nodes": [
                cid for cid in self._scc_ids if cid in pair_memory_nodes
            ],
            "evidence_pair_memory_edges": pair_memory_edges,
            "critical_pair_ledger_rows": critical_pair_rows,
            "critical_pair_locked_edges": [
                row for row in critical_pair_rows if row.get("state") == "locked"
            ],
            "critical_pair_candidate_edges": [
                row for row in critical_pair_rows if row.get("state") == "candidate"
            ],
            "critical_pair_revisit_history": list(self._critical_revisit_history),
            "critical_pair_policy": (
                "persistent critical-pair ledger with same-path severity features, "
                "hysteresis, evidence-guided revisits, and protected final-core "
                "coverage for locked pairs"
            ),
            "evidence_risk_subgraph_nodes": ordered_nodes,
            "evidence_risk_subgraph_size": len(ordered_nodes),
            "evidence_compression_ratio": 1 - (len(ordered_nodes) / total),
            "context_evidence_risk_subgraph_nodes": ordered_context_nodes,
            "context_evidence_risk_subgraph_size": len(ordered_context_nodes),
            "context_evidence_compression_ratio": (
                1 - (len(ordered_context_nodes) / total)
            ),
            "dynamic_core_priority_rows": dynamic_core_rows,
            "dynamic_core_hit_cap": len(ordered_nodes) >= cap,
            "dynamic_core_candidate_count": len(core_candidate_universe),
            "evidence_subgraph_policy": (
                "blind relation-first evidence accumulator with a dynamically "
                "maintained core risk subgraph. The core stops when marginal "
                "evidence drops, while context_evidence_* retains the older "
                "cap-bounded explanation subgraph."
            ),
            "evidence_subgraph_cap": cap,
            "relation_first_enabled": self.relation_first_enabled,
            "relation_evidence_policy": (
                "search selection uses progressive bias from relation evidence; "
                "probe windows revisit high-value pair/path frontiers without "
                "requiring endpoints to be individually high-risk"
            ),
        }

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

        local_pair_edges = []
        endpoint_counts: dict[str, int] = defaultdict(int)
        for (src, tgt), count in self._local_conflict_pair_counts.items():
            endpoint_counts[src] += count
            endpoint_counts[tgt] += count
            local_pair_edges.append({
                "source": src,
                "target": tgt,
                "count": count,
                "explicit_count": self._explicit_conflict_pair_counts.get((src, tgt), 0),
                "reasons": self._local_conflict_pair_reasons.get((src, tgt), []),
            })
        local_pair_edges.sort(key=lambda item: (-item["count"], item["source"], item["target"]))

        local_signal = {}
        for cid in self._scc_ids:
            local_signal[cid] = (
                self._local_subgraph_counts.get(cid, 0)
                + self._repair_entry_counts.get(cid, 0)
                + endpoint_counts.get(cid, 0)
            )
        ranking_by_local_subgraph = sorted(
            local_signal.items(),
            key=lambda item: (-item[1], item[0]),
        )
        local_subgraph_candidate_nodes = [
            cid for cid, signal in ranking_by_local_subgraph if signal > 0
        ]
        evidence_summary = self._build_evidence_summary(
            local_pair_edges=local_pair_edges,
            endpoint_counts=endpoint_counts,
        )

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
            "local_risk_subgraph_counts": dict(self._local_subgraph_counts),
            "repair_entry_counts": dict(self._repair_entry_counts),
            "local_conflict_edges": local_pair_edges,
            "local_subgraph_signal": local_signal,
            "local_subgraph_candidate_nodes": local_subgraph_candidate_nodes,
            "ranking_by_local_subgraph": ranking_by_local_subgraph,
            "amaf_node_evidence": dict(self._amaf_node_evidence),
            "amaf_edge_evidence": {
                f"{src}->{tgt}": value
                for (src, tgt), value in self._amaf_edge_evidence.items()
                if value > 0
            },
            "path_fragment_evidence": dict(self._path_fragment_evidence),
            "relation_node_raw_scores": self._relation_node_raw_scores(),
            "relation_probe_history": list(self._relation_probe_history),
            "relation_probe_count": len(self._relation_probe_history),
            "selection_events": list(self._selection_events),
            **evidence_summary,
            "trace_events": list(self._trace_events),
            "detection_log": self._detection_log,
            "time": elapsed,
        }
