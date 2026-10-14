"""Generate synthetic graphs with controlled topology for Ablation 1.

Three topologies:
  - DAG: pure acyclic (chain + branching)
  - Simple Cycle: single SCC of size K
  - Compound: multiple SCCs connected via DAG bridges
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class SyntheticNode:
    id: str
    ground_truth_risk: float = 0.3  # default "normal" risk
    is_anomaly: bool = False


@dataclass
class SyntheticEdge:
    source: str
    target: str


@dataclass
class SyntheticGraph:
    nodes: dict[str, SyntheticNode] = field(default_factory=dict)
    edges: list[SyntheticEdge] = field(default_factory=list)
    topology: str = "dag"
    scc_sizes: list[int] = field(default_factory=list)
    anomaly_nodes: list[str] = field(default_factory=list)

    @property
    def adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for e in self.edges:
            adj[e.source].append(e.target)
        return adj

    @property
    def node_ids(self) -> list[str]:
        return list(self.nodes.keys())


def generate_dag(n: int, anomaly_idx: int = -1, anomaly_risk: float = 0.6) -> SyntheticGraph:
    """Generate a pure DAG with n nodes (chain with some branches).

    Nodes: N0, N1, ..., N(n-1)
    Edges: Ni -> Ni+1 for main chain, plus some random forward edges.
    """
    graph = SyntheticGraph(topology="dag")

    for i in range(n):
        is_anomaly = (i == anomaly_idx) or (anomaly_idx == -1 and i == n - 2)
        risk = anomaly_risk if is_anomaly else random.uniform(0.25, 0.40)
        node = SyntheticNode(id=f"N{i}", ground_truth_risk=risk, is_anomaly=is_anomaly)
        graph.nodes[node.id] = node
        if is_anomaly:
            graph.anomaly_nodes.append(node.id)

    for i in range(n - 1):
        graph.edges.append(SyntheticEdge(source=f"N{i}", target=f"N{i+1}"))

    num_extra = max(1, n // 4)
    for _ in range(num_extra):
        i = random.randint(0, n - 3)
        j = random.randint(i + 2, n - 1)
        edge = SyntheticEdge(source=f"N{i}", target=f"N{j}")
        if not any(e.source == edge.source and e.target == edge.target for e in graph.edges):
            graph.edges.append(edge)

    return graph


def generate_simple_cycle(
    cycle_size: int,
    dag_prefix: int = 3,
    dag_suffix: int = 2,
    anomaly_pos: int = -1,
    anomaly_risk: float = 0.6,
) -> SyntheticGraph:
    """Generate a graph with a single SCC cycle of given size.

    Structure: [DAG prefix] -> [Cycle of cycle_size] -> [DAG suffix]
    """
    graph = SyntheticGraph(topology="simple_cycle")
    total = dag_prefix + cycle_size + dag_suffix
    node_counter = 0

    # DAG prefix
    prefix_ids = []
    for i in range(dag_prefix):
        nid = f"P{i}"
        graph.nodes[nid] = SyntheticNode(id=nid, ground_truth_risk=random.uniform(0.2, 0.35))
        prefix_ids.append(nid)
        node_counter += 1
    for i in range(dag_prefix - 1):
        graph.edges.append(SyntheticEdge(source=prefix_ids[i], target=prefix_ids[i + 1]))

    # Cycle (SCC)
    if anomaly_pos == -1:
        anomaly_pos = cycle_size // 2
    cycle_ids = []
    for i in range(cycle_size):
        nid = f"C{i}"
        is_anomaly = (i == anomaly_pos)
        risk = anomaly_risk if is_anomaly else random.uniform(0.25, 0.4)
        graph.nodes[nid] = SyntheticNode(id=nid, ground_truth_risk=risk, is_anomaly=is_anomaly)
        cycle_ids.append(nid)
        if is_anomaly:
            graph.anomaly_nodes.append(nid)
    for i in range(cycle_size):
        graph.edges.append(SyntheticEdge(
            source=cycle_ids[i],
            target=cycle_ids[(i + 1) % cycle_size],
        ))
    graph.scc_sizes.append(cycle_size)

    # Connect prefix -> cycle entry
    if prefix_ids:
        graph.edges.append(SyntheticEdge(source=prefix_ids[-1], target=cycle_ids[0]))

    # DAG suffix
    suffix_ids = []
    for i in range(dag_suffix):
        nid = f"S{i}"
        graph.nodes[nid] = SyntheticNode(id=nid, ground_truth_risk=random.uniform(0.2, 0.35))
        suffix_ids.append(nid)
    for i in range(dag_suffix - 1):
        graph.edges.append(SyntheticEdge(source=suffix_ids[i], target=suffix_ids[i + 1]))
    if suffix_ids:
        graph.edges.append(SyntheticEdge(source=cycle_ids[-1], target=suffix_ids[0]))

    return graph


def generate_compound_cycles(
    scc_sizes: list[int] | None = None,
    bridge_size: int = 2,
    anomaly_scc_idx: int = -1,
    anomaly_pos_in_scc: int = -1,
    anomaly_risk: float = 0.6,
) -> SyntheticGraph:
    """Generate a graph with multiple SCCs connected by DAG bridges.

    Structure: [SCC1] -> [bridge] -> [SCC2] -> [bridge] -> [SCC3] ...
    """
    if scc_sizes is None:
        scc_sizes = [4, 5, 3]

    if anomaly_scc_idx == -1:
        anomaly_scc_idx = len(scc_sizes) // 2

    graph = SyntheticGraph(topology="compound_cycle")
    prev_last_node = None

    for scc_idx, scc_size in enumerate(scc_sizes):
        # Bridge before SCC (except first)
        if scc_idx > 0 and bridge_size > 0:
            bridge_ids = []
            for b in range(bridge_size):
                nid = f"B{scc_idx}_{b}"
                graph.nodes[nid] = SyntheticNode(
                    id=nid, ground_truth_risk=random.uniform(0.2, 0.3)
                )
                bridge_ids.append(nid)
            for b in range(bridge_size - 1):
                graph.edges.append(SyntheticEdge(source=bridge_ids[b], target=bridge_ids[b + 1]))
            if prev_last_node:
                graph.edges.append(SyntheticEdge(source=prev_last_node, target=bridge_ids[0]))
            prev_last_node = bridge_ids[-1]

        # SCC
        anom_pos = anomaly_pos_in_scc if anomaly_pos_in_scc != -1 else scc_size // 2
        cycle_ids = []
        for i in range(scc_size):
            nid = f"SCC{scc_idx}_N{i}"
            is_anomaly = (scc_idx == anomaly_scc_idx and i == anom_pos)
            risk = anomaly_risk if is_anomaly else random.uniform(0.25, 0.4)
            graph.nodes[nid] = SyntheticNode(id=nid, ground_truth_risk=risk, is_anomaly=is_anomaly)
            cycle_ids.append(nid)
            if is_anomaly:
                graph.anomaly_nodes.append(nid)

        for i in range(scc_size):
            graph.edges.append(SyntheticEdge(
                source=cycle_ids[i], target=cycle_ids[(i + 1) % scc_size]
            ))
        # Add cross-edges within SCC to make it more connected
        if scc_size > 3:
            extra = random.randint(1, max(1, scc_size // 3))
            for _ in range(extra):
                a, b = random.sample(range(scc_size), 2)
                e = SyntheticEdge(source=cycle_ids[a], target=cycle_ids[b])
                if not any(x.source == e.source and x.target == e.target for x in graph.edges):
                    graph.edges.append(e)

        graph.scc_sizes.append(scc_size)

        # Connect bridge -> SCC entry
        if prev_last_node and scc_idx > 0:
            graph.edges.append(SyntheticEdge(source=prev_last_node, target=cycle_ids[0]))

        prev_last_node = cycle_ids[-1]

    return graph
