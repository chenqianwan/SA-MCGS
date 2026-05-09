"""Search methods for Ablation 1: True Tree-Based MCTS vs SA-MCGS.

M1: TreeMCTS - Standard Selection-Expansion-Rollout-Backprop on the graph.
    On cyclic graphs this exposes: tree explosion, rollout loops, Q-value dilution.
M4: SA-MCGS - SCC-aware window search with transposition table.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field

from experiments.ablation1_cycle.graph_generator import SyntheticGraph
from experiments.ablation1_cycle.mock_llm import MockEvaluator


@dataclass
class IterationRecord:
    iteration: int
    q_values: dict[str, float]  # per graph-node Q-values (aggregated across tree copies)
    visit_counts: dict[str, int]
    tree_size: int = 0
    rollout_steps: int = 0


@dataclass
class SearchResult:
    method: str
    topology: str
    graph_size: int
    scc_sizes: list[int]
    max_iterations: int
    actual_iterations: int
    final_q_values: dict[str, float]
    final_visit_counts: dict[str, int]
    target_rank: int | None
    hit_top3: bool
    # Tree-MCTS specific metrics
    tree_node_count: int = 0
    avg_rollout_steps: float = 0.0
    rollout_hit_cycle_rate: float = 0.0
    q_oscillation: float = 0.0
    q_spread: float = 0.0  # max Q - min Q: low = dilution failure
    visit_entropy: float = 0.0
    history: list[IterationRecord] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# M1: True Tree-Based MCTS
# ═══════════════════════════════════════════════════════════════════


@dataclass
class TreeNode:
    """A node in the MCTS search tree (NOT the same as a graph node).
    Multiple tree nodes can map to the same graph node (via different paths).
    """
    graph_node_id: str
    parent: TreeNode | None = None
    children: dict[str, TreeNode] = field(default_factory=dict)  # edge_target -> TreeNode
    visit_count: int = 0
    total_value: float = 0.0
    is_expanded: bool = False

    @property
    def q_value(self) -> float:
        return self.total_value / self.visit_count if self.visit_count > 0 else 0.0


class TreeMCTS:
    """M1: Standard MCTS with explicit search tree on graph.

    On DAG: works correctly - tree mirrors graph structure.
    On cyclic graphs: search tree EXPLODES because the same graph node
    appears as multiple tree nodes reached via different cycle traversals.
    Rollouts get stuck in cycles, returning uninformative truncated values.
    """

    def __init__(
        self,
        graph: SyntheticGraph,
        evaluator: MockEvaluator,
        max_iterations: int = 100,
        rollout_max_depth: int = 30,
        exploration_c: float = 1.414,
        **kwargs,
    ):
        self.graph = graph
        self.evaluator = evaluator
        self.max_iterations = max_iterations
        self.rollout_max_depth = rollout_max_depth
        self.exploration_c = exploration_c

        self.adj = graph.adjacency
        self.node_ids = list(graph.nodes.keys())

        # Pick a root (first node, or first prefix node)
        self.root = TreeNode(graph_node_id=self.node_ids[0])

        # Tracking metrics
        self.tree_node_count = 1
        self.rollout_steps_history: list[int] = []
        self.rollout_cycle_hits: int = 0
        self.total_rollouts: int = 0

        # Aggregate Q-values per graph node (across all tree copies)
        self.graph_node_visits: dict[str, int] = defaultdict(int)
        self.graph_node_total: dict[str, float] = defaultdict(float)
        self.graph_node_history: dict[str, list[float]] = defaultdict(list)

        self.history: list[IterationRecord] = []

    def run(self) -> SearchResult:
        for it in range(self.max_iterations):
            # 1. Selection: walk down tree using UCB until leaf
            leaf, path = self._select(self.root)

            # 2. Expansion: add one child to leaf
            child = self._expand(leaf)

            # 3. Rollout: random walk from child's graph node
            value, steps, hit_cycle = self._rollout(child.graph_node_id)
            self.rollout_steps_history.append(steps)
            self.total_rollouts += 1
            if hit_cycle:
                self.rollout_cycle_hits += 1

            # 4. Backpropagation: update all nodes on path
            self._backpropagate(path + [child], value)

            # Record state
            self._record(it)

        return self._build_result()

    def _select(self, node: TreeNode) -> tuple[TreeNode, list[TreeNode]]:
        """Walk down tree using UCB until we find an unexpanded node."""
        path = [node]
        current = node
        depth = 0
        max_select_depth = 100  # prevent infinite selection in deep trees

        while current.is_expanded and current.children and depth < max_select_depth:
            # UCB selection among children
            best_child = None
            best_ucb = -math.inf
            total_visits = current.visit_count + 1

            for child in current.children.values():
                if child.visit_count == 0:
                    best_child = child
                    break
                exploit = child.total_value / child.visit_count
                explore = self.exploration_c * math.sqrt(
                    math.log(total_visits) / child.visit_count
                )
                ucb = exploit + explore
                if ucb > best_ucb:
                    best_ucb = ucb
                    best_child = child

            if best_child is None:
                break

            current = best_child
            path.append(current)
            depth += 1

        return current, path

    def _expand(self, node: TreeNode) -> TreeNode:
        """Expand a leaf node by adding children for all outgoing edges."""
        graph_id = node.graph_node_id
        neighbors = self.adj.get(graph_id, [])

        if not neighbors:
            node.is_expanded = True
            return node

        # Add all children (even if they map to already-visited graph nodes!)
        # This is where tree EXPLOSION happens on cycles.
        for nbr_id in neighbors:
            if nbr_id not in node.children:
                child = TreeNode(graph_node_id=nbr_id, parent=node)
                node.children[nbr_id] = child
                self.tree_node_count += 1

        node.is_expanded = True

        # Return one unexplored child for rollout
        unvisited = [c for c in node.children.values() if c.visit_count == 0]
        if unvisited:
            return random.choice(unvisited)
        return random.choice(list(node.children.values()))

    def _rollout(self, start_graph_id: str) -> tuple[float, int, bool]:
        """Random rollout from a graph node. Returns (avg_risk, steps, hit_cycle).

        On cycles: the rollout keeps going around the cycle until max_depth.
        The returned value is an average of all visited nodes' risk scores,
        which in a cycle is just the cycle's average — NOT informative about
        which specific node is anomalous.
        """
        current = start_graph_id
        visited_in_rollout = set()
        visited_in_rollout.add(current)
        path_nodes = [current]
        hit_cycle = False

        for step in range(self.rollout_max_depth):
            neighbors = self.adj.get(current, [])
            if not neighbors:
                break
            next_node = random.choice(neighbors)

            if next_node in visited_in_rollout:
                hit_cycle = True
                # In standard MCTS there's no cycle detection — we just keep going

            visited_in_rollout.add(next_node)
            path_nodes.append(next_node)
            current = next_node

        # Evaluate: average risk of all nodes visited in rollout
        scores = self.evaluator.evaluate_window(list(set(path_nodes)))
        avg_value = sum(scores.values()) / len(scores) if scores else 0.5

        return avg_value, len(path_nodes), hit_cycle

    def _backpropagate(self, path: list[TreeNode], value: float):
        """Backpropagate value up the tree path."""
        for node in reversed(path):
            node.visit_count += 1
            node.total_value += value
            # Also track per-graph-node stats
            gid = node.graph_node_id
            self.graph_node_visits[gid] += 1
            self.graph_node_total[gid] += value
            self.graph_node_history[gid].append(value)

    def _record(self, iteration: int):
        q_values = {}
        visit_counts = {}
        for nid in self.node_ids:
            v = self.graph_node_visits[nid]
            visit_counts[nid] = v
            q_values[nid] = self.graph_node_total[nid] / v if v > 0 else 0.0

        self.history.append(IterationRecord(
            iteration=iteration,
            q_values=q_values.copy(),
            visit_counts=visit_counts.copy(),
            tree_size=self.tree_node_count,
            rollout_steps=self.rollout_steps_history[-1] if self.rollout_steps_history else 0,
        ))

    def _build_result(self) -> SearchResult:
        q_values = {}
        visit_counts = {}
        for nid in self.node_ids:
            v = self.graph_node_visits[nid]
            visit_counts[nid] = v
            q_values[nid] = self.graph_node_total[nid] / v if v > 0 else 0.0

        # Rank anomaly node
        ranked = sorted(q_values.items(), key=lambda x: -x[1])
        target_rank = None
        for rank, (nid, _) in enumerate(ranked, 1):
            if nid in self.graph.anomaly_nodes:
                target_rank = rank
                break

        # Q-value oscillation: std of last 20 values for anomaly node
        osc = 0.0
        if self.graph.anomaly_nodes:
            anom = self.graph.anomaly_nodes[0]
            hist = self.graph_node_history.get(anom, [])
            if len(hist) >= 10:
                tail = hist[-20:]
                mean = sum(tail) / len(tail)
                osc = math.sqrt(sum((v - mean) ** 2 for v in tail) / len(tail))

        # Q-value spread: max - min final Q-values
        # Low spread = all nodes indistinguishable = dilution failure
        q_vals_list = [v for v in q_values.values() if v > 0]
        q_spread = (max(q_vals_list) - min(q_vals_list)) if len(q_vals_list) >= 2 else 0.0

        # Visit entropy
        total_v = sum(visit_counts.values())
        entropy = 0.0
        if total_v > 0:
            for v in visit_counts.values():
                if v > 0:
                    p = v / total_v
                    entropy -= p * math.log2(p)

        avg_rollout = (
            sum(self.rollout_steps_history) / len(self.rollout_steps_history)
            if self.rollout_steps_history else 0
        )

        return SearchResult(
            method="tree_mcts",
            topology=self.graph.topology,
            graph_size=len(self.node_ids),
            scc_sizes=self.graph.scc_sizes,
            max_iterations=self.max_iterations,
            actual_iterations=len(self.history),
            final_q_values=q_values,
            final_visit_counts=visit_counts,
            target_rank=target_rank,
            hit_top3=(target_rank is not None and target_rank <= 3),
            tree_node_count=self.tree_node_count,
            avg_rollout_steps=avg_rollout,
            rollout_hit_cycle_rate=(
                self.rollout_cycle_hits / self.total_rollouts
                if self.total_rollouts > 0 else 0.0
            ),
            q_oscillation=osc,
            q_spread=q_spread,
            visit_entropy=entropy,
            history=self.history,
        )


# ═══════════════════════════════════════════════════════════════════
# M4: SA-MCGS (SCC-Aware Window Search)
# ═══════════════════════════════════════════════════════════════════


class SA_MCGS:
    """M4: SA-MCGS style search — SCC-aware windowed evaluation with TT.

    Avoids the three failure modes of TreeMCTS:
    1. No search tree → no tree explosion
    2. No rollout → no cycle-induced truncation waste
    3. Transposition table → same window evaluated once, reused
    4. SCC focus → concentrates budget on high-risk cyclic regions
    """

    def __init__(
        self,
        graph: SyntheticGraph,
        evaluator: MockEvaluator,
        max_iterations: int = 100,
        window_size: int = 4,
        exploration_c: float = 1.414,
        **kwargs,
    ):
        self.graph = graph
        self.evaluator = evaluator
        self.max_iterations = max_iterations
        self.window_size = window_size
        self.exploration_c = exploration_c

        self.node_ids = list(graph.nodes.keys())
        self.adj = graph.adjacency
        self.rev_adj: dict[str, list[str]] = defaultdict(list)
        for nid in self.node_ids:
            for tgt in self.adj[nid]:
                self.rev_adj[tgt].append(nid)

        self.visit_count: dict[str, int] = {nid: 0 for nid in self.node_ids}
        self.total_risk: dict[str, float] = {nid: 0.0 for nid in self.node_ids}
        self.risk_history: dict[str, list[float]] = defaultdict(list)

        self.transposition_table: dict[frozenset[str], dict[str, float]] = {}
        self.tt_hits = 0

        self.scc_nodes = self._detect_sccs()
        self.history: list[IterationRecord] = []

    def _detect_sccs(self) -> set[str]:
        """Find nodes that participate in any cycle."""
        scc_nodes = set()
        for nid in self.node_ids:
            if self._can_reach_self(nid):
                scc_nodes.add(nid)
        return scc_nodes

    def _can_reach_self(self, start: str, max_depth: int = 50) -> bool:
        visited = set()
        queue = list(self.adj.get(start, []))
        depth = 0
        while queue and depth < max_depth:
            next_queue = []
            for node in queue:
                if node == start:
                    return True
                if node not in visited:
                    visited.add(node)
                    next_queue.extend(self.adj.get(node, []))
            queue = next_queue
            depth += 1
        return False

    def run(self) -> SearchResult:
        for it in range(self.max_iterations):
            # Focus on SCC nodes
            if self.scc_nodes and random.random() < 0.8:
                seed = self._ucb_select_from(list(self.scc_nodes))
            else:
                seed = self._ucb_select_from(self.node_ids)

            window = self._build_window(seed)

            # TT lookup
            key = frozenset(window)
            if key in self.transposition_table:
                scores = self.transposition_table[key]
                self.tt_hits += 1
            else:
                scores = self.evaluator.evaluate_window(window)
                self.transposition_table[key] = scores

            for nid in window:
                score = scores.get(nid, 0.5)
                self.visit_count[nid] += 1
                self.total_risk[nid] += score
                self.risk_history[nid].append(score)

            self._record(it)

        return self._build_result()

    def _ucb_select_from(self, candidates: list[str]) -> str:
        total = sum(self.visit_count[c] for c in candidates) + 1
        best = None
        best_ucb = -math.inf
        for nid in candidates:
            n = self.visit_count[nid]
            if n == 0:
                return nid
            exploit = self.total_risk[nid] / n
            explore = self.exploration_c * math.sqrt(math.log(total) / n)
            ucb = exploit + explore
            if ucb > best_ucb:
                best_ucb = ucb
                best = nid
        return best

    def _build_window(self, seed: str) -> list[str]:
        window = [seed]
        window_set = {seed}
        for _ in range(self.window_size - 1):
            candidates = []
            for node in window:
                for nbr in self.adj.get(node, []):
                    if nbr not in window_set:
                        candidates.append(nbr)
                for nbr in self.rev_adj.get(node, []):
                    if nbr not in window_set:
                        candidates.append(nbr)
            if not candidates:
                break
            chosen = random.choice(candidates)
            window.append(chosen)
            window_set.add(chosen)
        return window

    def _record(self, iteration: int):
        q_values = {
            nid: (self.total_risk[nid] / self.visit_count[nid] if self.visit_count[nid] > 0 else 0.0)
            for nid in self.node_ids
        }
        self.history.append(IterationRecord(
            iteration=iteration,
            q_values=q_values.copy(),
            visit_counts=self.visit_count.copy(),
            tree_size=0,
            rollout_steps=0,
        ))

    def _build_result(self) -> SearchResult:
        q_values = {
            nid: (self.total_risk[nid] / self.visit_count[nid] if self.visit_count[nid] > 0 else 0.0)
            for nid in self.node_ids
        }
        visit_counts = self.visit_count.copy()

        ranked = sorted(q_values.items(), key=lambda x: -x[1])
        target_rank = None
        for rank, (nid, _) in enumerate(ranked, 1):
            if nid in self.graph.anomaly_nodes:
                target_rank = rank
                break

        osc = 0.0
        if self.graph.anomaly_nodes:
            anom = self.graph.anomaly_nodes[0]
            hist = self.risk_history.get(anom, [])
            if len(hist) >= 10:
                tail = hist[-20:]
                mean = sum(tail) / len(tail)
                osc = math.sqrt(sum((v - mean) ** 2 for v in tail) / len(tail))

        q_vals_list = [v for v in q_values.values() if v > 0]
        q_spread = (max(q_vals_list) - min(q_vals_list)) if len(q_vals_list) >= 2 else 0.0

        total_v = sum(visit_counts.values())
        entropy = 0.0
        if total_v > 0:
            for v in visit_counts.values():
                if v > 0:
                    p = v / total_v
                    entropy -= p * math.log2(p)

        return SearchResult(
            method="sa_mcgs",
            topology=self.graph.topology,
            graph_size=len(self.node_ids),
            scc_sizes=self.graph.scc_sizes,
            max_iterations=self.max_iterations,
            actual_iterations=len(self.history),
            final_q_values=q_values,
            final_visit_counts=visit_counts,
            target_rank=target_rank,
            hit_top3=(target_rank is not None and target_rank <= 3),
            tree_node_count=0,
            avg_rollout_steps=0.0,
            rollout_hit_cycle_rate=0.0,
            q_oscillation=osc,
            q_spread=q_spread,
            visit_entropy=entropy,
            history=self.history,
        )
