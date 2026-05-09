"""Merge same-company contracts into deal packages and analyze SCC growth."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.cuad_loader import CUADLoader
from src.models.graph import DependencyGraph, Edge, DependencyType
from src.models.clause import Clause
from src.modules.tarjan import TarjanSCCDetector
from experiments.run_clause_battle import add_medium_implicit_edges

FG_DIR = Path("data/cuad/grpo_lex_replicated/fullgraphs")

DEAL_PACKAGES = {
    "NETGEAR (Distributor+2Amend)": [
        "NETGEAR_INC_04_21_2003-EX-10.16-DISTRIBUTOR_AGREEMENT_fullgraph.json",
        "NETGEAR_INC_04_21_2003-EX-10.16-AMENDMENT_TO_THE_DISTRIBUTOR_AGREEMENT_BETWEEN_INGRAM_MICRO_AND_NETGEAR_fullgraph.json",
        "NETGEAR_INC_04_21_2003-EX-10.16-_AMENDMENT_2_TO_THE_DISTRIBUTION_AGREEMENT_fullgraph.json",
    ],
    "Gpaq (License+Service)": [
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.6_11951677_EX-10.6_License_Agreement_fullgraph.json",
        "GpaqAcquisitionHoldingsInc_20200123_S-4A_EX-10.8_11951679_EX-10.8_Service_Agreement_fullgraph.json",
    ],
    "Reynolds (Supply+Service)": [
        "ReynoldsConsumerProductsInc_20191115_S-1_EX-10.18_11896469_EX-10.18_Supply_Agreement_fullgraph.json",
        "ReynoldsConsumerProductsInc_20200121_S-1A_EX-10.22_11948918_EX-10.22_Service_Agreement_fullgraph.json",
    ],
    "Bellring (4xManufacturing)": [
        "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing_Agreement1_fullgraph.json",
        "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing_Agreement2_fullgraph.json",
        "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing_Agreement3_fullgraph.json",
        "BellringBrandsInc_20190920_S-1_EX-10.12_11817081_EX-10.12_Manufacturing_Agreement4_fullgraph.json",
    ],
    "BioAmber (Dev+Amendment)": [
        "BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT_AGREEMENT_1_fullgraph.json",
        "BIOAMBERINC_04_10_2013-EX-10.34-DEVELOPMENT_AGREEMENT_-_First_Amendment_fullgraph.json",
    ],
    "AzulSa (2xMaintenance)": [
        "AzulSa_20170303_F-1A_EX-10.3_9943903_EX-10.3_Maintenance_Agreement1_fullgraph.json",
        "AzulSa_20170303_F-1A_EX-10.3_9943903_EX-10.3_Maintenance_Agreement2_fullgraph.json",
    ],
}


def add_cross_contract_edges(merged_graph: DependencyGraph) -> list[Edge]:
    """Add edges between contracts based on shared defined terms."""
    term_definers: dict[str, list[str]] = {}
    term_users: dict[str, list[str]] = {}

    for clause_id, clause in merged_graph.clauses.items():
        node_type = clause.metadata.get("node_type", "")
        if node_type == "DEFINED_TERM":
            term_name = (clause.title or clause.id).lower().strip()
            term_definers.setdefault(term_name, []).append(clause_id)

    for edge in merged_graph.edges:
        if edge.reasoning in ("DEFINES", "USES"):
            target = merged_graph.clauses.get(edge.target)
            if target and target.metadata.get("node_type") == "DEFINED_TERM":
                term_name = (target.title or target.id).lower().strip()
                if edge.reasoning == "USES":
                    term_users.setdefault(term_name, []).append(edge.source)

    cross_edges = []
    existing = {(e.source, e.target) for e in merged_graph.edges}
    stopwords = {
        "party", "parties", "agreement", "company", "date", "section",
        "term", "terms", "notice", "the", "this agreement",
    }

    for term_name, definers in term_definers.items():
        if term_name in stopwords or len(term_name) <= 2:
            continue
        users = term_users.get(term_name, [])
        if not users:
            continue

        for user_id in users:
            user_c = merged_graph.clauses.get(user_id)
            if not user_c:
                continue
            user_src = user_c.metadata.get("_source_contract", "")

            for definer_id in definers:
                definer_c = merged_graph.clauses.get(definer_id)
                if not definer_c:
                    continue
                definer_src = definer_c.metadata.get("_source_contract", "")

                if user_src != definer_src and (user_id, definer_id) not in existing:
                    cross_edges.append(Edge(
                        source=user_id, target=definer_id,
                        dependency_type=DependencyType.REFERENCES,
                        weight=0.6, reasoning="CROSS_CONTRACT_TERM",
                    ))
                    existing.add((user_id, definer_id))

    # Also connect CLAUSE nodes that reference the same section numbers across contracts
    clause_by_section: dict[str, list[str]] = {}
    for cid, clause in merged_graph.clauses.items():
        if clause.metadata.get("node_type") == "CLAUSE":
            orig = clause.metadata.get("_original_id", "")
            if orig and not orig.startswith("term:") and not orig.startswith("party:"):
                clause_by_section.setdefault(orig, []).append(cid)

    for section, nodes in clause_by_section.items():
        if len(nodes) < 2:
            continue
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                ci = merged_graph.clauses[nodes[i]]
                cj = merged_graph.clauses[nodes[j]]
                if ci.metadata.get("_source_contract") != cj.metadata.get("_source_contract"):
                    for pair in [(nodes[i], nodes[j]), (nodes[j], nodes[i])]:
                        if pair not in existing:
                            cross_edges.append(Edge(
                                source=pair[0], target=pair[1],
                                dependency_type=DependencyType.REFERENCES,
                                weight=0.7, reasoning="CROSS_CONTRACT_SAME_SECTION",
                            ))
                            existing.add(pair)

    return cross_edges


def merge_graphs(graphs: list[tuple[str, DependencyGraph]]) -> DependencyGraph:
    """Merge graphs, keeping term: prefix visible for implicit edge detection."""
    merged_clauses: dict[str, Clause] = {}
    merged_edges: list[Edge] = []

    for idx, (cid, g) in enumerate(graphs):
        tag = f"C{idx}"
        for clause_id, clause in g.clauses.items():
            if clause_id.startswith("term:"):
                new_id = f"term:{tag}_{clause_id[5:]}"
            elif clause_id.startswith("party:"):
                new_id = f"party:{tag}_{clause_id[6:]}"
            else:
                new_id = f"{tag}_{clause_id}"
            new_c = clause.model_copy()
            new_c.id = new_id
            new_c.metadata["_source_contract"] = cid
            new_c.metadata["_original_id"] = clause_id
            new_c.metadata["_contract_idx"] = idx
            merged_clauses[new_id] = new_c

        id_map = {}
        for clause_id in g.clauses:
            if clause_id.startswith("term:"):
                id_map[clause_id] = f"term:{tag}_{clause_id[5:]}"
            elif clause_id.startswith("party:"):
                id_map[clause_id] = f"party:{tag}_{clause_id[6:]}"
            else:
                id_map[clause_id] = f"{tag}_{clause_id}"

        for edge in g.edges:
            new_src = id_map.get(edge.source, f"{tag}_{edge.source}")
            new_tgt = id_map.get(edge.target, f"{tag}_{edge.target}")
            new_e = edge.model_copy()
            new_e.source = new_src
            new_e.target = new_tgt
            merged_edges.append(new_e)

    return DependencyGraph(clauses=merged_clauses, edges=merged_edges)


def main():
    loader = CUADLoader(str(FG_DIR.parent), config={"cuad": {"clause_only": False}})
    tarjan = TarjanSCCDetector()

    print("=" * 100)
    print("CROSS-CONTRACT SCC ANALYSIS: Deal Package Merging")
    print("=" * 100)

    for pkg_name, files in DEAL_PACKAGES.items():
        print(f"\n{'='*80}")
        print(f"  {pkg_name}")
        print(f"{'='*80}")

        graphs = []
        for fname in files:
            fpath = FG_DIR / fname
            if not fpath.exists():
                print(f"  MISSING: {fname}")
                continue
            result = loader.load_single_graph(fpath)
            if result:
                cid, g = result
                graphs.append((cid, g))
                print(f"  Loaded: {cid[:55]} -> {len(g.clauses)} nodes, {len(g.edges)} edges")

        if len(graphs) < 2:
            print("  SKIP: need >= 2 graphs")
            continue

        # Individual SCC analysis
        print(f"\n  --- Individual SCCs (with medium implicit) ---")
        individual_max = 0
        for cid, g in graphs:
            gc = g.model_copy(deep=True)
            gc = add_medium_implicit_edges(gc)
            gc = tarjan.detect(gc)
            mx = max((s.size for s in gc.sccs), default=0)
            total = sum(s.size for s in gc.sccs)
            individual_max = max(individual_max, mx)
            print(f"    {cid[:45]}: SCCs={len(gc.sccs)}, max={mx}, total={total}/{len(gc.clauses)}")

        # Merge
        merged = merge_graphs(graphs)
        cross_edges = add_cross_contract_edges(merged)
        merged.edges.extend(cross_edges)
        merged = add_medium_implicit_edges(merged)
        merged = tarjan.detect(merged)

        merged_max = max((s.size for s in merged.sccs), default=0)
        merged_total = sum(s.size for s in merged.sccs)

        print(f"\n  --- MERGED RESULT ---")
        print(f"    Nodes: {len(merged.clauses)}")
        print(f"    Edges: {len(merged.edges)} (incl {len(cross_edges)} cross-contract)")
        print(f"    SCCs: {len(merged.sccs)}, max_size={merged_max}, total_scc_nodes={merged_total}")
        print(f"    GROWTH: max SCC {individual_max} -> {merged_max} ({'+' if merged_max > individual_max else ''}{merged_max - individual_max})")

        if merged.sccs:
            for scc in sorted(merged.sccs, key=lambda s: -s.size)[:5]:
                contracts_in_scc = set()
                for nid in scc.clause_ids:
                    c = merged.clauses.get(nid)
                    if c:
                        contracts_in_scc.add(c.metadata.get("_source_contract", "?")[:35])
                cross = len(contracts_in_scc) > 1
                marker = " *** CROSS-CONTRACT ***" if cross else ""
                print(f"      SCC(size={scc.size}) contracts={contracts_in_scc}{marker}")


if __name__ == "__main__":
    main()
