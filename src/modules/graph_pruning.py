"""Domain-Informed Graph Pruning (workflow Step 4, ⭐ Core Contribution)

在 Tarjan SCC 检测之前对依赖图进行剪枝，包含五个策略：

Legacy (heuristic):
  1. Noise Edge Removal  — 过滤 LLM 提取的假阳性边
  2. Hierarchical Prior   — 强制 Def→Obl→Cond→Rem→Lim 层级结构
  3. Information Bottleneck — min I(G';G) - β·I(G';Y) 压缩图同时保留任务信号

New (principled):
  4. Functional Graph Coarsening (FGC) — 坍缩直通节点, 保留语义等价性
  5. Type-Aware Cycle Saliency (TACS)  — 基于边语义类型区分良性/恶性环路
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import networkx as nx
from loguru import logger

from ..models.clause import CLAUSE_TYPE_HIERARCHY, Clause, ClauseType
from ..models.graph import DependencyGraph, DependencyType, Edge


# =========================================================================
# 1. Noise Edge Removal
# =========================================================================

class NoiseEdgeRemover:
    """过滤 LLM 提取中的假阳性边。

    策略:
    - 低权重边 (weight < threshold)
    - 自环
    - 重复推理 (不同边但 reasoning 完全相同 → 疑似幻觉)
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.weight_threshold = gp_cfg.get("noise_weight_threshold", 0.35)
        self.remove_duplicate_reasoning = gp_cfg.get("remove_duplicate_reasoning", True)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        original = len(graph.edges)
        kept: list[Edge] = []
        seen_reasoning: set[str] = set()
        removed_low_weight = 0
        removed_self_loop = 0
        removed_dup_reason = 0

        for e in graph.edges:
            if e.source == e.target:
                removed_self_loop += 1
                continue
            if e.weight < self.weight_threshold:
                removed_low_weight += 1
                continue
            if self.remove_duplicate_reasoning and e.reasoning:
                key = e.reasoning.strip().lower()
                if key in seen_reasoning:
                    removed_dup_reason += 1
                    continue
                seen_reasoning.add(key)
            kept.append(e)

        graph.edges = kept
        stats = {
            "original": original,
            "kept": len(kept),
            "removed_low_weight": removed_low_weight,
            "removed_self_loop": removed_self_loop,
            "removed_dup_reasoning": removed_dup_reason,
        }
        logger.info(f"Noise edge removal: {original} → {len(kept)} edges ({stats})")
        return stats


# =========================================================================
# 2. Hierarchical Prior Enforcement
# =========================================================================

class HierarchicalPriorEnforcer:
    """强制条款层级先验: Definition → Obligation → Condition → Remedy → Limitation

    层级中较高层的条款应当被较低层引用（被依赖），而不是反过来。
    如果一条边的方向违反层级顺序且权重较低，则移除。
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.violation_weight_threshold = gp_cfg.get("hierarchy_violation_threshold", 0.6)
        self._rank = {ct: i for i, ct in enumerate(CLAUSE_TYPE_HIERARCHY)}

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        original = len(graph.edges)
        kept: list[Edge] = []
        removed = 0

        for e in graph.edges:
            src_clause = graph.clauses.get(e.source)
            tgt_clause = graph.clauses.get(e.target)

            if not src_clause or not tgt_clause:
                kept.append(e)
                continue

            src_rank = self._rank.get(src_clause.clause_type, 99)
            tgt_rank = self._rank.get(tgt_clause.clause_type, 99)

            # edge: source → target 表示 target 依赖 source
            # 合法方向: 高层级(低rank) 被 低层级(高rank) 依赖 → src_rank <= tgt_rank
            # 违反: src_rank > tgt_rank 且权重低
            if src_rank > tgt_rank and e.weight < self.violation_weight_threshold:
                removed += 1
                continue

            kept.append(e)

        graph.edges = kept
        stats = {"original": original, "kept": len(kept), "removed_violations": removed}
        logger.info(f"Hierarchical prior: removed {removed} hierarchy-violating edges")
        return stats


# =========================================================================
# 3. Information Bottleneck Pruning
# =========================================================================

class InfoBottleneckPruner:
    """Information Bottleneck: min I(G';G) - β·I(G';Y)

    近似实现: 对每条边计算 "task relevance" (基于图结构重要性)，
    贪心移除 relevance 最低的边直到达到压缩目标。
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.compression_ratio = gp_cfg.get("ib_compression_ratio", 0.15)
        self.beta = gp_cfg.get("ib_beta", 1.0)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        if not graph.edges:
            return {"original": 0, "kept": 0, "removed": 0}

        original = len(graph.edges)
        target_remove = max(1, int(original * self.compression_ratio))

        G = nx.DiGraph()
        for cid in graph.clauses:
            G.add_node(cid)
        for e in graph.edges:
            G.add_edge(e.source, e.target, weight=e.weight)

        edge_scores: list[tuple[int, float]] = []
        for idx, e in enumerate(graph.edges):
            score = self._edge_relevance(e, G, graph)
            edge_scores.append((idx, score))

        edge_scores.sort(key=lambda x: x[1])

        remove_indices: set[int] = set()
        for idx, score in edge_scores:
            if len(remove_indices) >= target_remove:
                break
            remove_indices.add(idx)

        graph.edges = [e for i, e in enumerate(graph.edges) if i not in remove_indices]
        stats = {"original": original, "kept": len(graph.edges), "removed": len(remove_indices)}
        logger.info(f"Info bottleneck: removed {len(remove_indices)} low-relevance edges "
                     f"(compression={self.compression_ratio:.0%})")
        return stats

    def _edge_relevance(self, edge: Edge, G: nx.DiGraph, graph: DependencyGraph) -> float:
        """近似 I(G';Y): 边对下游 SCC 结构和连通性的贡献度"""
        weight_score = edge.weight

        src_out = G.out_degree(edge.source)
        tgt_in = G.in_degree(edge.target)
        redundancy = min(src_out, tgt_in)
        structural_score = 1.0 / (1.0 + redundancy)

        # 如果这条边是 bridge（移除后增加连通分量），relevance 高
        bridge_bonus = 0.0
        G_temp = G.copy()
        G_temp.remove_edge(edge.source, edge.target)
        if not nx.has_path(G_temp, edge.source, edge.target):
            bridge_bonus = 0.5

        relevance = self.beta * (weight_score * 0.4 + structural_score * 0.3 + bridge_bonus * 0.3)
        return relevance


# =========================================================================
# 4. Functional Graph Coarsening (FGC)
# =========================================================================

# Edge types that carry independent normative weight (not just pass-through)
_SUBSTANTIVE_EDGE_TYPES = {DependencyType.CONSTRAINS, DependencyType.TRIGGERS, DependencyType.MODIFIES}
_REFERENCE_EDGE_TYPES = {DependencyType.DEFINES, DependencyType.REFERENCES}

# Clause types that are "substantive" (carry obligations/prohibitions/rights)
_SUBSTANTIVE_CLAUSE_TYPES = {ClauseType.OBLIGATION, ClauseType.CONDITION, ClauseType.REMEDY, ClauseType.LIMITATION}


class FunctionalGraphCoarsener:
    """Functional Graph Coarsening: collapse pass-through chains.

    A node is "pass-through" if:
      1. It has exactly 1 incoming and 1 outgoing edge within a local
         neighborhood (SCC-like cluster), AND
      2. It is NOT substantive (i.e., it's a definition or pure reference), AND
      3. Both its edges are weak (DEFINES / REFERENCES type).

    When A → B → C and B is pass-through, collapse into A → C with a
    virtual edge that inherits min(weight_AB, weight_BC).

    This preserves logical reachability while reducing graph diameter.
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.enabled = gp_cfg.get("fgc_enabled", True)
        self.max_chain_length = gp_cfg.get("fgc_max_chain", 5)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        G = nx.DiGraph()
        edge_map: dict[tuple[str, str], Edge] = {}
        for e in graph.edges:
            G.add_edge(e.source, e.target)
            edge_map[(e.source, e.target)] = e

        pass_through_nodes: set[str] = set()
        for nid in list(G.nodes):
            clause = graph.clauses.get(nid)
            if not clause:
                continue
            in_deg = G.in_degree(nid)
            out_deg = G.out_degree(nid)
            if in_deg != 1 or out_deg != 1:
                continue
            if clause.clause_type in _SUBSTANTIVE_CLAUSE_TYPES:
                continue
            pred = list(G.predecessors(nid))[0]
            succ = list(G.successors(nid))[0]
            e_in = edge_map.get((pred, nid))
            e_out = edge_map.get((nid, succ))
            if not e_in or not e_out:
                continue
            if e_in.dependency_type in _REFERENCE_EDGE_TYPES and e_out.dependency_type in _REFERENCE_EDGE_TYPES:
                pass_through_nodes.add(nid)

        virtual_edges: list[Edge] = []
        collapsed_chains: list[list[str]] = []
        processed: set[str] = set()

        for pt in sorted(pass_through_nodes):
            if pt in processed:
                continue
            chain = [pt]
            processed.add(pt)

            current = pt
            for _ in range(self.max_chain_length):
                succ = list(G.successors(current))[0]
                if succ in pass_through_nodes and succ not in processed:
                    chain.append(succ)
                    processed.add(succ)
                    current = succ
                else:
                    break

            current = pt
            for _ in range(self.max_chain_length):
                pred = list(G.predecessors(current))[0]
                if pred in pass_through_nodes and pred not in processed:
                    chain.insert(0, pred)
                    processed.add(pred)
                    current = pred
                else:
                    break

            first_pt = chain[0]
            last_pt = chain[-1]
            chain_start = list(G.predecessors(first_pt))[0]
            chain_end = list(G.successors(last_pt))[0]

            weights = []
            e = edge_map.get((chain_start, first_pt))
            if e:
                weights.append(e.weight)
            for i in range(len(chain) - 1):
                e = edge_map.get((chain[i], chain[i + 1]))
                if e:
                    weights.append(e.weight)
            e = edge_map.get((last_pt, chain_end))
            if e:
                weights.append(e.weight)

            virtual_edge = Edge(
                source=chain_start,
                target=chain_end,
                dependency_type=DependencyType.REFERENCES,
                weight=min(weights) if weights else 0.5,
                reasoning=f"[FGC] collapsed chain: {chain_start}→{'→'.join(chain)}→{chain_end}",
            )
            virtual_edges.append(virtual_edge)
            collapsed_chains.append([chain_start] + chain + [chain_end])

        new_edges = [
            e for e in graph.edges
            if e.source not in pass_through_nodes and e.target not in pass_through_nodes
        ]
        existing_pairs = {(e.source, e.target) for e in new_edges}
        for ve in virtual_edges:
            if (ve.source, ve.target) not in existing_pairs:
                new_edges.append(ve)
                existing_pairs.add((ve.source, ve.target))

        removed_edges = len(graph.edges) - len(new_edges)
        graph.edges = new_edges

        for nid in pass_through_nodes:
            graph.clauses[nid].metadata["_fgc_collapsed"] = True

        stats = {
            "pass_through_nodes": len(pass_through_nodes),
            "collapsed_chains": len(collapsed_chains),
            "virtual_edges_added": len(virtual_edges),
            "edges_removed": removed_edges,
            "chains": [[n for n in c] for c in collapsed_chains[:5]],
        }
        logger.info(
            f"FGC: collapsed {len(pass_through_nodes)} pass-through nodes "
            f"into {len(virtual_edges)} virtual edges "
            f"(net edge delta: {-removed_edges + len(virtual_edges):+d})"
        )
        return stats


# =========================================================================
# 5. Type-Aware Cycle Saliency (TACS)
# =========================================================================

# Conflict strength by edge type (higher = more likely to cause real conflict)
_EDGE_CONFLICT_STRENGTH = {
    DependencyType.CONSTRAINS: 1.0,
    DependencyType.TRIGGERS: 0.9,
    DependencyType.MODIFIES: 0.8,
    DependencyType.DEFINES: 0.3,
    DependencyType.REFERENCES: 0.1,
}


class TypeAwareCycleSaliency:
    """Type-Aware Cycle Saliency: distinguish benign vs. conflict cycles.

    For each simple cycle in the graph (up to a length limit):
      1. Compute cycle_saliency = min(conflict_strength(e) for e in cycle)
      2. If cycle_saliency < threshold, the cycle is "benign" (just
         cross-references) — break it by removing the weakest edge.

    This targets the root cause of SCC complexity: not all cycles represent
    real logical conflicts. Many are just mutual references that don't
    create normative tension.
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.enabled = gp_cfg.get("tacs_enabled", True)
        self.saliency_threshold = gp_cfg.get("tacs_saliency_threshold", 0.4)
        self.max_cycle_length = gp_cfg.get("tacs_max_cycle_length", 6)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        G = nx.DiGraph()
        edge_lookup: dict[tuple[str, str], Edge] = {}
        for e in graph.edges:
            G.add_edge(e.source, e.target)
            edge_lookup[(e.source, e.target)] = e

        edges_to_remove: set[tuple[str, str]] = set()
        benign_cycles = 0
        conflict_cycles = 0

        try:
            cycles = list(nx.simple_cycles(G, length_bound=self.max_cycle_length))
        except Exception:
            cycles = []

        for cycle in cycles:
            if len(cycle) < 2:
                continue
            cycle_edges = []
            for i in range(len(cycle)):
                src = cycle[i]
                tgt = cycle[(i + 1) % len(cycle)]
                e = edge_lookup.get((src, tgt))
                if e:
                    cycle_edges.append(e)

            if not cycle_edges:
                continue

            saliencies = [
                _EDGE_CONFLICT_STRENGTH.get(e.dependency_type, 0.5)
                for e in cycle_edges
            ]
            cycle_saliency = min(saliencies)

            if cycle_saliency < self.saliency_threshold:
                benign_cycles += 1
                weakest = min(cycle_edges, key=lambda e: (
                    _EDGE_CONFLICT_STRENGTH.get(e.dependency_type, 0.5),
                    e.weight,
                ))
                edges_to_remove.add((weakest.source, weakest.target))
            else:
                conflict_cycles += 1

        graph.edges = [
            e for e in graph.edges
            if (e.source, e.target) not in edges_to_remove
        ]

        stats = {
            "total_cycles_analyzed": len(cycles),
            "benign_cycles": benign_cycles,
            "conflict_cycles": conflict_cycles,
            "edges_removed": len(edges_to_remove),
            "removed_edges": [f"{s}→{t}" for s, t in list(edges_to_remove)[:10]],
        }
        logger.info(
            f"TACS: analyzed {len(cycles)} cycles, "
            f"benign={benign_cycles}, conflict={conflict_cycles}, "
            f"removed {len(edges_to_remove)} weak cycle edges"
        )
        return stats


# =========================================================================
# 6. Edge Type Enrichment (ETE) — Plan A
# =========================================================================

class EdgeTypeEnricher:
    """Enrich homogeneous REFERENCES edges using heuristic clause-pair analysis.

    When all edges in a subgraph are REFERENCES (no type diversity),
    upgrade edges to CONSTRAINS/TRIGGERS based on clause content signals:
      - If target clause contains obligation/prohibition keywords → CONSTRAINS
      - If source clause defines a condition that target depends on → TRIGGERS
      - Otherwise keep as REFERENCES
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.enabled = gp_cfg.get("ete_enabled", True)

    _OBLIGATION_KEYWORDS = {
        "verpflichtet", "muss", "shall", "must", "obligation", "required",
        "darf nicht", "prohibited", "verboten", "pflicht", "haftet",
        "schuldet", "gewährleisten", "sicherstellen",
    }
    _CONDITION_KEYWORDS = {
        "wenn", "falls", "sofern", "soweit", "unter der voraussetzung",
        "if", "provided that", "subject to", "condition", "voraussetzung",
        "es sei denn", "unless", "except",
    }

    def enrich(self, graph: DependencyGraph) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        upgraded_constrains = 0
        upgraded_triggers = 0
        total = len(graph.edges)

        for e in graph.edges:
            if e.dependency_type != DependencyType.REFERENCES:
                continue
            tgt_clause = graph.clauses.get(e.target)
            src_clause = graph.clauses.get(e.source)
            if not tgt_clause or not src_clause:
                continue

            tgt_text = (tgt_clause.content or "").lower()
            src_text = (src_clause.content or "").lower()

            if any(kw in tgt_text for kw in self._OBLIGATION_KEYWORDS):
                e.dependency_type = DependencyType.CONSTRAINS
                upgraded_constrains += 1
            elif any(kw in src_text for kw in self._CONDITION_KEYWORDS):
                e.dependency_type = DependencyType.TRIGGERS
                upgraded_triggers += 1

        stats = {
            "total_edges": total,
            "upgraded_constrains": upgraded_constrains,
            "upgraded_triggers": upgraded_triggers,
            "unchanged": total - upgraded_constrains - upgraded_triggers,
        }
        logger.info(
            f"ETE: enriched {upgraded_constrains} → CONSTRAINS, "
            f"{upgraded_triggers} → TRIGGERS, "
            f"{stats['unchanged']} unchanged"
        )
        return stats


# =========================================================================
# 7. Adaptive TACS — Plan B
# =========================================================================

class AdaptiveTACS:
    """Adaptive TACS: falls back to topology-based pruning when edge types are homogeneous.

    When edge type diversity is low (>80% same type), instead of using
    conflict_strength, rank cycle edges by betweenness centrality.
    Only remove edges with LOW centrality (redundant paths), preserving
    high-centrality edges that form the structural backbone.

    Also applies a budget: never remove more than `max_removal_ratio` of edges.
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.enabled = gp_cfg.get("adaptive_tacs_enabled", True)
        self.saliency_threshold = gp_cfg.get("adaptive_tacs_saliency", 0.4)
        self.max_cycle_length = gp_cfg.get("adaptive_tacs_max_cycle", 6)
        self.max_removal_ratio = gp_cfg.get("adaptive_tacs_max_removal", 0.35)
        self.homogeneity_threshold = gp_cfg.get("adaptive_tacs_homogeneity", 0.80)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        G = nx.DiGraph()
        edge_lookup: dict[tuple[str, str], Edge] = {}
        for e in graph.edges:
            G.add_edge(e.source, e.target)
            edge_lookup[(e.source, e.target)] = e

        type_counts: dict[DependencyType, int] = defaultdict(int)
        for e in graph.edges:
            type_counts[e.dependency_type] += 1
        total_edges = len(graph.edges)
        max_type_ratio = max(type_counts.values()) / max(total_edges, 1)
        is_homogeneous = max_type_ratio >= self.homogeneity_threshold

        edge_centrality = nx.edge_betweenness_centrality(G)

        try:
            cycles = list(nx.simple_cycles(G, length_bound=self.max_cycle_length))
        except Exception:
            cycles = []

        edges_to_remove: set[tuple[str, str]] = set()
        max_removable = int(total_edges * self.max_removal_ratio)
        benign = 0
        conflict = 0

        for cycle in cycles:
            if len(cycle) < 2 or len(edges_to_remove) >= max_removable:
                continue

            cycle_edges = []
            for i in range(len(cycle)):
                src, tgt = cycle[i], cycle[(i + 1) % len(cycle)]
                e = edge_lookup.get((src, tgt))
                if e:
                    cycle_edges.append(e)
            if not cycle_edges:
                continue

            if is_homogeneous:
                centralities = [
                    edge_centrality.get((e.source, e.target), 0)
                    for e in cycle_edges
                ]
                cycle_importance = min(centralities)
                median_centrality = sorted(edge_centrality.values())[len(edge_centrality) // 2] if edge_centrality else 0.01
                if cycle_importance < median_centrality * 0.5:
                    benign += 1
                    weakest = min(cycle_edges, key=lambda e: (
                        edge_centrality.get((e.source, e.target), 0), e.weight
                    ))
                    edges_to_remove.add((weakest.source, weakest.target))
                else:
                    conflict += 1
            else:
                saliencies = [
                    _EDGE_CONFLICT_STRENGTH.get(e.dependency_type, 0.5)
                    for e in cycle_edges
                ]
                if min(saliencies) < self.saliency_threshold:
                    benign += 1
                    weakest = min(cycle_edges, key=lambda e: (
                        _EDGE_CONFLICT_STRENGTH.get(e.dependency_type, 0.5), e.weight
                    ))
                    edges_to_remove.add((weakest.source, weakest.target))
                else:
                    conflict += 1

        graph.edges = [
            e for e in graph.edges
            if (e.source, e.target) not in edges_to_remove
        ]

        stats = {
            "is_homogeneous": is_homogeneous,
            "max_type_ratio": round(max_type_ratio, 2),
            "fallback_mode": "centrality" if is_homogeneous else "type_saliency",
            "total_cycles": len(cycles),
            "benign": benign,
            "conflict": conflict,
            "edges_removed": len(edges_to_remove),
            "removal_budget": max_removable,
            "removed_edges": [f"{s}→{t}" for s, t in list(edges_to_remove)[:10]],
        }
        logger.info(
            f"AdaptiveTACS [{stats['fallback_mode']}]: "
            f"{len(cycles)} cycles, benign={benign}, conflict={conflict}, "
            f"removed {len(edges_to_remove)}/{max_removable} (budget)"
        )
        return stats


# =========================================================================
# 8. Soft TACS — Plan C
# =========================================================================

class SoftTACS:
    """Soft TACS: don't delete edges, just reweight them by saliency.

    Instead of hard pruning, multiply each edge's weight by its
    cycle-saliency score. Low-saliency edges get downweighted,
    making MCGS naturally avoid them during UCB selection.

    Nodes stay in the SCC but "cold" paths become less attractive.
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.enabled = gp_cfg.get("soft_tacs_enabled", True)
        self.max_cycle_length = gp_cfg.get("soft_tacs_max_cycle", 6)
        self.decay_factor = gp_cfg.get("soft_tacs_decay", 0.5)

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}

        G = nx.DiGraph()
        edge_lookup: dict[tuple[str, str], Edge] = {}
        for e in graph.edges:
            G.add_edge(e.source, e.target)
            edge_lookup[(e.source, e.target)] = e

        edge_in_benign_count: dict[tuple[str, str], int] = defaultdict(int)
        edge_in_any_count: dict[tuple[str, str], int] = defaultdict(int)

        try:
            cycles = list(nx.simple_cycles(G, length_bound=self.max_cycle_length))
        except Exception:
            cycles = []

        benign = 0
        for cycle in cycles:
            if len(cycle) < 2:
                continue
            cycle_pairs = []
            all_weak = True
            for i in range(len(cycle)):
                src, tgt = cycle[i], cycle[(i + 1) % len(cycle)]
                cycle_pairs.append((src, tgt))
                e = edge_lookup.get((src, tgt))
                if e and _EDGE_CONFLICT_STRENGTH.get(e.dependency_type, 0.5) >= 0.4:
                    all_weak = False

            for pair in cycle_pairs:
                edge_in_any_count[pair] += 1
                if all_weak:
                    edge_in_benign_count[pair] += 1

            if all_weak:
                benign += 1

        reweighted = 0
        for e in graph.edges:
            key = (e.source, e.target)
            total = edge_in_any_count.get(key, 0)
            benign_c = edge_in_benign_count.get(key, 0)
            if total > 0 and benign_c > 0:
                benign_ratio = benign_c / total
                dampening = 1.0 - (benign_ratio * self.decay_factor)
                e.weight = round(e.weight * max(dampening, 0.1), 4)
                reweighted += 1

        stats = {
            "total_cycles": len(cycles),
            "benign_cycles": benign,
            "edges_reweighted": reweighted,
            "total_edges": len(graph.edges),
        }
        logger.info(
            f"SoftTACS: {len(cycles)} cycles, {benign} benign, "
            f"reweighted {reweighted}/{len(graph.edges)} edges"
        )
        return stats


# =========================================================================
# Orchestrator: Domain-Informed Graph Pruner
# =========================================================================

class DomainGraphPruner:
    """编排 Domain-Informed Graph Pruning。

    Supports two loading modes:

    1. **Plugin mode** (recommended): set ``graph_pruning.plugins`` to a list
       of registered plugin names, e.g. ``["legacy", "plan_b"]``.  Each plugin
       is loaded from the registry and executed sequentially.

    2. **Legacy mode** (backward-compatible): set ``graph_pruning.mode`` to one
       of ``legacy / new / full / plan_a / plan_b / plan_c / plan_a_tacs``.
       Falls back to the old if-chain when ``plugins`` is absent.
    """

    def __init__(self, config: dict):
        gp_cfg = config.get("graph_pruning", {})
        self.enabled = gp_cfg.get("enabled", True)
        self.mode = gp_cfg.get("mode", "legacy")

        # ── Plugin mode: lazy-load only requested strategies ──
        self._plugins: list | None = None
        plugin_names: list[str] | None = gp_cfg.get("plugins")
        if plugin_names is not None:
            self._import_plugin_modules()
            from .pruning.base import GraphPruningPlugin
            self._plugins = [
                GraphPruningPlugin.get(name)(config) for name in plugin_names
            ]
            logger.info(
                f"DomainGraphPruner: loaded {len(self._plugins)} plugin(s): "
                f"{plugin_names}"
            )
        else:
            # ── Legacy mode: instantiate everything up front ──
            self.noise_remover = NoiseEdgeRemover(config)
            self.hierarchy_enforcer = HierarchicalPriorEnforcer(config)
            self.ib_pruner = InfoBottleneckPruner(config)
            self.fgc = FunctionalGraphCoarsener(config)
            self.tacs = TypeAwareCycleSaliency(config)
            self.ete = EdgeTypeEnricher(config)
            self.adaptive_tacs = AdaptiveTACS(config)
            self.soft_tacs = SoftTACS(config)

    @staticmethod
    def _import_plugin_modules():
        """Import built-in plugin modules so they self-register."""
        import importlib
        for mod_name in (
            "src.modules.pruning.legacy_plugin",
            "src.modules.pruning.adaptive_tacs_plugin",
            "src.modules.pruning.cross_domain_plugin",
        ):
            try:
                importlib.import_module(mod_name)
            except ImportError:
                pass

    def prune(self, graph: DependencyGraph) -> dict[str, Any]:
        if not self.enabled:
            logger.info("Domain graph pruning: disabled")
            return {"enabled": False}

        original_edge_count = len(graph.edges)

        # ── Plugin path ──
        if self._plugins is not None:
            all_stats: dict[str, Any] = {"mode": "plugins"}
            for plugin in self._plugins:
                plugin_stats = plugin.prune(graph)
                all_stats.update(plugin_stats)
        else:
            # ── Legacy if-chain (backward-compatible) ──
            all_stats = {"mode": self.mode}
            if self.mode in ("legacy", "full"):
                all_stats["noise"] = self.noise_remover.prune(graph)
                all_stats["hierarchy"] = self.hierarchy_enforcer.prune(graph)
                all_stats["info_bottleneck"] = self.ib_pruner.prune(graph)
            if self.mode in ("new", "full"):
                all_stats["fgc"] = self.fgc.prune(graph)
                all_stats["tacs"] = self.tacs.prune(graph)
            if self.mode == "plan_a":
                all_stats["ete"] = self.ete.enrich(graph)
                all_stats["tacs"] = self.tacs.prune(graph)
            if self.mode == "plan_b":
                all_stats["adaptive_tacs"] = self.adaptive_tacs.prune(graph)
            if self.mode == "plan_c":
                all_stats["soft_tacs"] = self.soft_tacs.prune(graph)
            if self.mode == "plan_a_tacs":
                all_stats["ete"] = self.ete.enrich(graph)
                all_stats["adaptive_tacs"] = self.adaptive_tacs.prune(graph)

        final_edge_count = len(graph.edges)
        total_removed = original_edge_count - final_edge_count

        all_stats.update({
            "original_edges": original_edge_count,
            "final_edges": final_edge_count,
            "total_removed": total_removed,
            "removal_rate": round(total_removed / max(original_edge_count, 1), 4),
        })
        mode_label = "plugins" if self._plugins else self.mode
        logger.info(
            f"Domain graph pruning [{mode_label}]: "
            f"{original_edge_count} → {final_edge_count} edges "
            f"({all_stats['removal_rate']:.1%} removed)"
        )
        return all_stats
