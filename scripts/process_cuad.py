"""Process CUAD contracts into SA-MCGS DependencyGraph format.

This script:
1. Reads raw CUAD contract text files
2. Segments into clauses (rule-based)
3. Extracts cross-references
4. Builds DependencyGraph objects
5. Saves as .gpickle.gz (same format as QuantLaw, loadable by pipeline)

Usage:
    python -m scripts.process_cuad                        # process all 510 contracts
    python -m scripts.process_cuad --subset distribut     # only distribution contracts
    python -m scripts.process_cuad --subset grpo          # the 43 graph-grpo-lex subset
    python -m scripts.process_cuad --single path/to.txt   # single contract
"""
from __future__ import annotations

import gzip
import json
import pickle
import sys
from pathlib import Path

import networkx as nx
import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data.cuad_loader import CUADLoader
from src.models.graph import DependencyGraph

CUAD_TXT_DIR = Path("data/cuad/CUAD_v1/CUAD_v1/full_contract_txt")
OUTPUT_DIR = Path("data/cuad/processed")

GRPO_CONTRACT_NAMES = [
    "ACCURAYINC_09_01_2010-EX-10.31-DISTRIBUTOR AGREEMENT",
    "ADAMSGOLFINC_03_21_2005-EX-10.17-ENDORSEMENT AGREEMENT",
    "ADIANUTRITION,INC_04_01_2005-EX-10.D2-RESELLER AGREEMENT",
    "AIRSPANNETWORKSINC_04_11_2000-EX-10.5-Distributor Agreement",
    "AIRTECHINTERNATIONALGROUPINC_05_08_2000-EX-10.4-FRANCHISE AGREEMENT",
]


def graph_to_gpickle(graph: DependencyGraph, output_path: Path) -> None:
    """Save DependencyGraph as .gpickle.gz (QuantLaw-compatible)."""
    G = nx.DiGraph()
    for cid, clause in graph.clauses.items():
        G.add_node(
            cid,
            heading=clause.title,
            text=clause.content,
            key=cid,
            clause_type=clause.clause_type.value,
            **clause.metadata,
        )
    for edge in graph.edges:
        G.add_edge(
            edge.source,
            edge.target,
            edge_type=edge.dependency_type.value,
            weight=edge.weight,
            reasoning=edge.reasoning,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output_path, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)


def graph_to_json(graph: DependencyGraph, output_path: Path) -> dict:
    """Save DependencyGraph as JSON (human-readable)."""
    data = {
        "contract_id": graph.metadata.get("graph_id", "unknown"),
        "metadata": graph.metadata,
        "stats": {
            "num_clauses": len(graph.clauses),
            "num_edges": len(graph.edges),
            "clause_types": {},
            "edge_types": {},
        },
        "clauses": [],
        "edges": [],
    }
    for cid, clause in graph.clauses.items():
        ct = clause.clause_type.value
        data["stats"]["clause_types"][ct] = data["stats"]["clause_types"].get(ct, 0) + 1
        data["clauses"].append({
            "id": cid,
            "title": clause.title,
            "content": clause.content[:200],
            "clause_type": ct,
        })
    for edge in graph.edges:
        et = edge.dependency_type.value
        data["stats"]["edge_types"][et] = data["stats"]["edge_types"].get(et, 0) + 1
        data["edges"].append({
            "source": edge.source,
            "target": edge.target,
            "type": et,
            "weight": edge.weight,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return data["stats"]


app = typer.Typer()


@app.command()
def main(
    subset: str = typer.Option(
        "distribut",
        help="Filter: 'all'=510 contracts, 'distribut'=distribution subset, 'grpo'=graph-grpo-lex 43",
    ),
    single: str = typer.Option(None, help="Process a single contract file"),
    output_dir: str = typer.Option(str(OUTPUT_DIR), help="Output directory"),
    txt_dir: str = typer.Option(str(CUAD_TXT_DIR), help="CUAD text files directory"),
):
    """Process CUAD contracts into SA-MCGS graph format."""
    out = Path(output_dir)
    gpickle_dir = out / "gpickle"
    json_dir = out / "json"
    gpickle_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    loader = CUADLoader("data/cuad")

    if single:
        result = loader.load_single_text(single)
        if result:
            cid, graph = result
            graph_to_gpickle(graph, gpickle_dir / f"{cid}.gpickle.gz")
            stats = graph_to_json(graph, json_dir / f"{cid}.json")
            logger.info(f"Processed {cid}: {stats}")
        else:
            logger.error(f"Failed to process {single}")
        return

    txt_path = Path(txt_dir)
    if not txt_path.exists():
        logger.error(f"CUAD text directory not found: {txt_path}")
        logger.info("Run: cd data/cuad && curl -L -o CUAD_v1.zip 'https://zenodo.org/records/4595826/files/CUAD_v1.zip?download=1' && unzip CUAD_v1.zip")
        raise typer.Exit(1)

    txt_files = sorted(txt_path.glob("*.txt"))
    logger.info(f"Found {len(txt_files)} contract text files")

    if subset == "grpo":
        txt_files = [f for f in txt_files if any(n in f.stem for n in GRPO_CONTRACT_NAMES)]
    elif subset != "all":
        txt_files = [f for f in txt_files if subset.lower() in f.stem.lower()]

    logger.info(f"Processing {len(txt_files)} contracts (subset='{subset}')")

    summary = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "total_clauses": 0,
        "total_edges": 0,
        "contracts": [],
    }

    for i, txt_file in enumerate(txt_files):
        summary["total"] += 1
        contract_id = txt_file.stem

        result = loader.load_single_text(txt_file)
        if result:
            cid, graph = result
            graph_to_gpickle(graph, gpickle_dir / f"{cid}.gpickle.gz")
            stats = graph_to_json(graph, json_dir / f"{cid}.json")

            summary["success"] += 1
            summary["total_clauses"] += stats["num_clauses"]
            summary["total_edges"] += stats["num_edges"]
            summary["contracts"].append({
                "id": cid,
                **stats,
            })

            if (i + 1) % 20 == 0 or (i + 1) == len(txt_files):
                logger.info(
                    f"[{i+1}/{len(txt_files)}] {cid}: "
                    f"{stats['num_clauses']} clauses, {stats['num_edges']} edges"
                )
        else:
            summary["failed"] += 1
            logger.warning(f"[{i+1}/{len(txt_files)}] Failed: {contract_id}")

    with open(out / "processing_summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    logger.info("=" * 60)
    logger.info(f"CUAD Processing Complete")
    logger.info(f"  Contracts: {summary['success']}/{summary['total']} successful")
    logger.info(f"  Total clauses: {summary['total_clauses']}")
    logger.info(f"  Total edges: {summary['total_edges']}")
    logger.info(f"  Avg clauses/contract: {summary['total_clauses'] / max(1, summary['success']):.1f}")
    logger.info(f"  Avg edges/contract: {summary['total_edges'] / max(1, summary['success']):.1f}")
    logger.info(f"  Output: {out}")
    logger.info(f"  gpickle: {gpickle_dir} (loadable by QuantLawLoader)")
    logger.info(f"  json: {json_dir} (human-readable)")


if __name__ == "__main__":
    app()
