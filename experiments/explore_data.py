"""Phase 0: Load QuantLaw DE 2019 graph, explore SCC structure, select perturbation targets.

Usage:
    python -m experiments.explore_data --data-dir data/quantlaw

Output:
    experiments/data/graph_stats_2019.json
    experiments/data/experiment_targets.json
"""
from __future__ import annotations

import gzip
import json
import pickle
import random
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx
import typer
from loguru import logger

app = typer.Typer()


def _find_gpickle(data_dir: Path) -> Path:
    """Locate the 2019 DE cross-reference graph file."""
    candidates = [
        data_dir / "de" / "4_crossreference_graph" / "2019.gpickle.gz",
        data_dir / "de" / "4_crossreference_graph" / "2019.gpickle",
    ]
    for p in candidates:
        if p.exists():
            return p

    # Fallback: glob for any 2019 file
    for p in data_dir.rglob("*2019*gpickle*"):
        return p

    # If no 2019, pick the latest year available
    gpickles = sorted(data_dir.rglob("*.gpickle.gz"))
    if gpickles:
        logger.warning(f"2019 not found; using latest available: {gpickles[-1].name}")
        return gpickles[-1]

    raise FileNotFoundError(
        f"No .gpickle.gz files found under {data_dir}. "
        "Run: cd data/quantlaw && zenodo_get 4660133"
    )


def load_raw_graph(filepath: Path) -> nx.DiGraph:
    """Load a gzipped or plain NetworkX pickle."""
    if filepath.suffix == ".gz":
        with gzip.open(filepath, "rb") as f:
            G = pickle.load(f)
    else:
        with open(filepath, "rb") as f:
            G = pickle.load(f)
    if not isinstance(G, nx.DiGraph):
        G = nx.DiGraph(G)
    return G


def filter_hierarchy_edges(
    G: nx.DiGraph,
    hierarchy_keywords: set[str] | None = None,
) -> tuple[nx.DiGraph, int]:
    """Remove hierarchy/containment edges, keeping only cross-references."""
    if hierarchy_keywords is None:
        hierarchy_keywords = {"containment", "hierarchy", "part_of"}

    to_remove = []
    for u, v, d in G.edges(data=True):
        etype = str(d.get("edge_type", d.get("type", ""))).lower()
        if etype in hierarchy_keywords:
            to_remove.append((u, v))

    G.remove_edges_from(to_remove)

    isolates = list(nx.isolates(G))
    G.remove_nodes_from(isolates)

    return G, len(to_remove)


def explore_graph(G: nx.DiGraph) -> dict[str, Any]:
    """Compute structural statistics of the filtered graph."""
    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()
    density = nx.density(G) if n_nodes > 1 else 0.0

    raw_sccs = list(nx.strongly_connected_components(G))
    nontrivial_sccs = []
    dag_nodes = []

    for scc_nodes in raw_sccs:
        if len(scc_nodes) == 1:
            node = next(iter(scc_nodes))
            if G.has_edge(node, node):
                nontrivial_sccs.append(sorted(scc_nodes))
            else:
                dag_nodes.append(node)
        else:
            nontrivial_sccs.append(sorted(scc_nodes))

    scc_sizes = sorted([len(s) for s in nontrivial_sccs], reverse=True)
    size_distribution = dict(Counter(scc_sizes))
    dag_ratio = len(dag_nodes) / n_nodes if n_nodes > 0 else 0.0
    giant_scc_size = scc_sizes[0] if scc_sizes else 0

    # Edge attribute field names (for config verification)
    edge_attrs: set[str] = set()
    for _, _, d in list(G.edges(data=True))[:100]:
        edge_attrs.update(d.keys())

    # Node attribute field names
    node_attrs: set[str] = set()
    for _, d in list(G.nodes(data=True))[:100]:
        node_attrs.update(d.keys())

    # Sample SCC details
    scc_details = []
    for i, scc_nodes in enumerate(nontrivial_sccs[:5]):
        details = {"scc_index": i, "size": len(scc_nodes), "nodes": []}
        for nid in scc_nodes[:6]:
            nd = G.nodes.get(nid, {})
            details["nodes"].append({
                "id": str(nid),
                "heading": nd.get("heading", nd.get("title", "")),
                "key": nd.get("key", nd.get("section", "")),
                "has_text": bool(nd.get("text", nd.get("content", ""))),
            })
        scc_details.append(details)

    return {
        "num_nodes": n_nodes,
        "num_edges": n_edges,
        "density": round(density, 6),
        "num_nontrivial_sccs": len(nontrivial_sccs),
        "num_dag_nodes": len(dag_nodes),
        "dag_ratio": round(dag_ratio, 4),
        "giant_scc_size": giant_scc_size,
        "scc_size_distribution": size_distribution,
        "scc_sizes_top10": scc_sizes[:10],
        "edge_attribute_fields": sorted(edge_attrs),
        "node_attribute_fields": sorted(node_attrs),
        "scc_sample_details": scc_details,
        "_nontrivial_sccs": nontrivial_sccs,
        "_dag_nodes": dag_nodes,
    }


def select_targets(
    G: nx.DiGraph,
    stats: dict[str, Any],
    num_dag_targets: int = 10,
    num_scc_targets: int = 3,
    preferred_scc_size_range: tuple[int, int] = (3, 8),
) -> dict[str, Any]:
    """Select perturbation targets from DAG nodes and SCCs."""
    nontrivial_sccs = stats["_nontrivial_sccs"]
    dag_nodes = stats["_dag_nodes"]

    # --- DAG targets: prefer nodes with text content ---
    dag_with_text = []
    dag_without_text = []
    for nid in dag_nodes:
        nd = G.nodes.get(nid, {})
        has_text = bool(nd.get("text", nd.get("content", "")))
        heading = nd.get("heading", nd.get("title", ""))
        has_heading = bool(heading)
        if has_text or has_heading:
            dag_with_text.append(str(nid))
        else:
            dag_without_text.append(str(nid))

    random.seed(42)
    pool = dag_with_text if len(dag_with_text) >= num_dag_targets else dag_with_text + dag_without_text
    dag_targets = random.sample(pool, min(num_dag_targets, len(pool)))

    # --- SCC targets: prefer size 3-8, pick largest within range ---
    min_sz, max_sz = preferred_scc_size_range
    good_sccs = sorted(
        [s for s in nontrivial_sccs if min_sz <= len(s) <= max_sz],
        key=len, reverse=True,
    )
    if len(good_sccs) < num_scc_targets:
        good_sccs = sorted(nontrivial_sccs, key=len, reverse=True)

    scc_targets = []
    for scc_nodes in good_sccs[:num_scc_targets]:
        scc_id = f"scc_target_{len(scc_targets)}"
        node_details = []
        for nid in scc_nodes:
            nd = G.nodes.get(nid, {})
            node_details.append({
                "id": str(nid),
                "heading": nd.get("heading", nd.get("title", str(nid))),
                "key": nd.get("key", nd.get("section", "")),
                "has_text": bool(nd.get("text", nd.get("content", ""))),
            })

        # Find internal edges for this SCC
        scc_set = set(str(n) for n in scc_nodes)
        internal_edges = []
        for u, v in G.edges():
            if str(u) in scc_set and str(v) in scc_set:
                internal_edges.append({"source": str(u), "target": str(v)})

        scc_targets.append({
            "scc_id": scc_id,
            "size": len(scc_nodes),
            "node_ids": [str(n) for n in scc_nodes],
            "nodes": node_details,
            "internal_edges": internal_edges,
        })

    # Prepare DAG target details
    dag_target_details = []
    for nid in dag_targets:
        nd = G.nodes.get(nid, G.nodes.get(int(nid) if nid.isdigit() else nid, {}))
        dag_target_details.append({
            "id": nid,
            "heading": nd.get("heading", nd.get("title", nid)),
            "key": nd.get("key", nd.get("section", "")),
            "has_text": bool(nd.get("text", nd.get("content", ""))),
        })

    return {
        "dag_targets": dag_target_details,
        "scc_targets": scc_targets,
    }


@app.command()
def main(
    data_dir: str = typer.Option("data/quantlaw", help="QuantLaw data root"),
    output_dir: str = typer.Option("experiments/data", help="Output directory"),
    num_dag: int = typer.Option(10, help="Number of DAG target nodes"),
    num_scc: int = typer.Option(3, help="Number of target SCCs"),
):
    """Explore the QuantLaw DE 2019 graph and select experiment targets."""
    data_path = Path(data_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Step 0.1: Find and load
    gpickle_path = _find_gpickle(data_path)
    logger.info(f"Loading graph from {gpickle_path}")
    G = load_raw_graph(gpickle_path)
    logger.info(f"Raw graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Step 0.2: Filter and explore
    G, n_removed = filter_hierarchy_edges(G)
    logger.info(f"Filtered {n_removed} hierarchy edges; remaining: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    stats = explore_graph(G)

    # Print summary
    print("\n" + "=" * 60)
    print("QuantLaw DE 2019 — Graph Structure Summary")
    print("=" * 60)
    print(f"  Nodes:              {stats['num_nodes']:,}")
    print(f"  Edges:              {stats['num_edges']:,}")
    print(f"  Density:            {stats['density']:.6f}")
    print(f"  Non-trivial SCCs:   {stats['num_nontrivial_sccs']}")
    print(f"  DAG nodes:          {stats['num_dag_nodes']:,}")
    print(f"  DAG ratio:          {stats['dag_ratio']:.2%}")
    print(f"  Giant SCC size:     {stats['giant_scc_size']}")
    print(f"  SCC sizes (top 10): {stats['scc_sizes_top10']}")
    print(f"  Edge attrs:         {stats['edge_attribute_fields']}")
    print(f"  Node attrs:         {stats['node_attribute_fields']}")

    if stats["scc_sample_details"]:
        print("\n  Sample SCC details:")
        for scc in stats["scc_sample_details"][:3]:
            print(f"    SCC #{scc['scc_index']} (size={scc['size']}):")
            for node in scc["nodes"][:3]:
                print(f"      - {node['id']}: heading='{node['heading']}', has_text={node['has_text']}")
    print("=" * 60)

    # Save stats (without internal data)
    stats_export = {k: v for k, v in stats.items() if not k.startswith("_")}
    stats_file = out_path / "graph_stats_2019.json"
    stats_file.write_text(json.dumps(stats_export, indent=2, ensure_ascii=False, default=str))
    logger.info(f"Saved graph stats to {stats_file}")

    # Step 0.3: Select targets
    targets = select_targets(G, stats, num_dag_targets=num_dag, num_scc_targets=num_scc)
    targets_file = out_path / "experiment_targets.json"
    targets_file.write_text(json.dumps(targets, indent=2, ensure_ascii=False, default=str))
    logger.info(f"Saved experiment targets to {targets_file}")

    print(f"\n  DAG targets selected: {len(targets['dag_targets'])}")
    print(f"  SCC targets selected: {len(targets['scc_targets'])}")
    for scc in targets["scc_targets"]:
        print(f"    {scc['scc_id']}: size={scc['size']}, edges={len(scc['internal_edges'])}")


if __name__ == "__main__":
    app()
