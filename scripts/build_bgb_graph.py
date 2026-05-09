"""Build a real BGB cross-reference graph from gesetze-im-internet.de XML.

Uses the `quantlaw` package to extract legal references from the full text
of the German Civil Code (BGB). Outputs a NetworkX DiGraph in the same
.gpickle.gz format expected by QuantLawLoader.

Usage:
    python scripts/build_bgb_graph.py
"""
from __future__ import annotations

import gzip
import pickle
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import networkx as nx
from quantlaw.de_extract.statutes_areas import StatutesExtractor
from quantlaw.de_extract.statutes_parse import StatutesParser
from quantlaw.de_extract.stemming import stem_law_name

ROOT = Path(__file__).resolve().parent.parent
XML_PATH = ROOT / "data" / "bgb_raw" / "BJNR001950896.xml"
OUT_DIR = ROOT / "data" / "quantlaw" / "de" / "4_crossreference_graph"
OUT_FILE = OUT_DIR / "2019.gpickle.gz"

# §-number normalisation: "§ 123a" -> "123a"
SECTION_NUM_RE = re.compile(r"§\s*(\d+\w*)")


def parse_bgb_xml(xml_path: Path) -> dict[str, dict]:
    """Parse BGB XML into a dict of section_number -> {title, text, doknr}."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    sections: dict[str, dict] = {}

    for norm in root.findall("norm"):
        meta = norm.find("metadaten")
        if meta is None:
            continue

        enbez_elem = meta.find("enbez")
        if enbez_elem is None or not enbez_elem.text:
            continue

        enbez = enbez_elem.text.strip()
        if not enbez.startswith("§"):
            continue

        m = SECTION_NUM_RE.match(enbez)
        if not m:
            continue
        sec_num = m.group(1)

        titel_elem = meta.find("titel")
        title = titel_elem.text.strip() if titel_elem is not None and titel_elem.text else ""

        text_elem = norm.find(".//textdaten/text")
        if text_elem is None:
            continue
        full_text = ET.tostring(text_elem, encoding="unicode", method="text").strip()

        if not full_text or full_text == "(weggefallen)":
            continue

        doknr = norm.attrib.get("doknr", "")

        sections[sec_num] = {
            "title": title,
            "text": full_text,
            "doknr": doknr,
            "enbez": enbez,
        }

    return sections


def extract_references(
    sections: dict[str, dict],
) -> list[tuple[str, str]]:
    """Use quantlaw to extract cross-references between BGB sections.

    Returns a list of (source_section, target_section) tuples.
    """
    laws_lookup = {stem_law_name("BGB"): "bgb", stem_law_name("Bürgerliches Gesetzbuch"): "bgb"}
    extractor = StatutesExtractor(laws_lookup)
    parser = StatutesParser(laws_lookup)

    valid_sections = set(sections.keys())
    edges: list[tuple[str, str]] = []
    stats = defaultdict(int)

    for sec_num, sec_data in sections.items():
        text = sec_data["text"]
        stats["sections_processed"] += 1

        for match in extractor.find_all(text):
            if not match.has_main_area():
                continue

            law_type = match.law_match_type
            if law_type not in ("internal", "dict"):
                continue

            main_text = match.main_text()
            try:
                parsed = parser.parse_main(main_text)
            except Exception:
                stats["parse_errors"] += 1
                continue

            ref_nums = _extract_section_numbers_from_parsed(parsed)

            for ref_num in ref_nums:
                if ref_num in valid_sections and ref_num != sec_num:
                    edges.append((sec_num, ref_num))
                    stats["edges_found"] += 1

    edges = list(set(edges))
    stats["unique_edges"] = len(edges)

    print(f"Reference extraction stats:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")

    return edges


def _extract_section_numbers_from_parsed(parsed: list[list[list[str]]]) -> list[str]:
    """Extract § section numbers from quantlaw parser output.

    The parser returns nested lists like:
    [[['§', '26'], ['Abs', '2']], [['§', '27'], ['Abs', '1']]]

    We only want the § unit values, not Abs/Satz/Nr values.
    """
    numbers = []
    for ref_path in parsed:
        for unit, val in ref_path:
            if unit == "§":
                numbers.append(val)
    return numbers


def build_graph(
    sections: dict[str, dict],
    edges: list[tuple[str, str]],
) -> nx.DiGraph:
    """Build a NetworkX DiGraph compatible with QuantLawLoader."""
    connected_nodes = set()
    for u, v in edges:
        connected_nodes.add(u)
        connected_nodes.add(v)

    G = nx.DiGraph(name="bgb_2019")

    for sec_num in connected_nodes:
        sec_data = sections[sec_num]
        node_id = f"bgb_{sec_num}"
        G.add_node(
            node_id,
            heading=f"§{sec_num} {sec_data['title']}",
            key=f"BGB_§{sec_num}",
            text=sec_data["text"],
            document_type="section",
            section_number=sec_num,
            doknr=sec_data["doknr"],
        )

    sec_to_node = {sec_num: f"bgb_{sec_num}" for sec_num in connected_nodes}

    for src, tgt in edges:
        G.add_edge(sec_to_node[src], sec_to_node[tgt], edge_type="reference")

    return G


def save_graph(G: nx.DiGraph, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_path, "wb") as f:
        pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Saved graph to {out_path} ({size_mb:.1f} MB)")


def analyze_graph(G: nx.DiGraph) -> None:
    """Print detailed graph statistics."""
    print(f"\n{'='*60}")
    print(f"BGB Cross-Reference Graph Statistics")
    print(f"{'='*60}")
    print(f"Nodes: {G.number_of_nodes()}")
    print(f"Edges: {G.number_of_edges()}")
    print(f"Density: {nx.density(G):.6f}")

    in_degrees = [d for _, d in G.in_degree()]
    out_degrees = [d for _, d in G.out_degree()]
    print(f"\nIn-degree:  min={min(in_degrees)}, max={max(in_degrees)}, "
          f"avg={sum(in_degrees)/len(in_degrees):.1f}")
    print(f"Out-degree: min={min(out_degrees)}, max={max(out_degrees)}, "
          f"avg={sum(out_degrees)/len(out_degrees):.1f}")

    sccs = list(nx.strongly_connected_components(G))
    scc_sizes = sorted([len(s) for s in sccs], reverse=True)
    non_trivial = [s for s in scc_sizes if s > 1]
    print(f"\nStrongly Connected Components:")
    print(f"  Total: {len(sccs)}")
    print(f"  Non-trivial (size > 1): {len(non_trivial)}")
    if non_trivial:
        print(f"  Largest SCC: {non_trivial[0]} nodes")
        print(f"  Top-5 SCC sizes: {non_trivial[:5]}")

    wccs = list(nx.weakly_connected_components(G))
    wcc_sizes = sorted([len(s) for s in wccs], reverse=True)
    print(f"\nWeakly Connected Components:")
    print(f"  Total: {len(wccs)}")
    print(f"  Largest WCC: {wcc_sizes[0]} nodes ({wcc_sizes[0]/G.number_of_nodes()*100:.1f}%)")

    text_lengths = [len(G.nodes[n].get("text", "")) for n in G.nodes()]
    print(f"\nText lengths:")
    print(f"  min={min(text_lengths)}, max={max(text_lengths)}, "
          f"avg={sum(text_lengths)/len(text_lengths):.0f}")
    total_chars = sum(text_lengths)
    print(f"  Total: {total_chars:,} characters ({total_chars/1000:.0f}K)")

    top_in = sorted(G.in_degree(), key=lambda x: x[1], reverse=True)[:10]
    print(f"\nTop-10 most referenced sections:")
    for node, deg in top_in:
        heading = G.nodes[node].get("heading", node)
        print(f"  {heading}: {deg} incoming references")

    top_out = sorted(G.out_degree(), key=lambda x: x[1], reverse=True)[:5]
    print(f"\nTop-5 sections with most outgoing references:")
    for node, deg in top_out:
        heading = G.nodes[node].get("heading", node)
        print(f"  {heading}: {deg} outgoing references")


def main():
    print(f"Loading BGB XML from {XML_PATH} ...")
    sections = parse_bgb_xml(XML_PATH)
    print(f"Parsed {len(sections)} BGB sections with text")

    print(f"\nExtracting cross-references with quantlaw ...")
    edges = extract_references(sections)

    print(f"\nBuilding graph ...")
    G = build_graph(sections, edges)
    analyze_graph(G)

    print(f"\nSaving graph ...")
    save_graph(G, OUT_FILE)
    print("\nDone!")


if __name__ == "__main__":
    main()
