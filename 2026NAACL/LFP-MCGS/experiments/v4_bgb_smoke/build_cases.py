#!/usr/bin/env python3
"""Build deterministic BGB SCC controlled-intervention smoke cases.

This builder intentionally separates model-visible ``public_case`` records from
evaluator-only formal programs and gold labels.  It never edits the source
graph or the BGB XML.  Every intervention is an append-only, delimited note,
and every original window is retained with a SHA-256 digest.

Run from anywhere:

    python 2026NAACL/LFP-MCGS/experiments/v4_bgb_smoke/build_cases.py
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import pickle
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import networkx as nx


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
DEFAULT_CONFIG = HERE / "config.json"
PUBLIC_SCHEMA = "bgb-scc-public-case-v1"
GOLD_SCHEMA = "bgb-scc-gold-sidecar-v1"
COMBINED_SCHEMA = "bgb-scc-combined-case-v1"
MANIFEST_SCHEMA = "bgb-scc-manifest-v1"
LABEL_ENTAILED = "Entailed"
LABEL_UNKNOWN = "PR-Unknown"


def canonical_json(value: Any) -> str:
    """Return the one canonical JSON representation used by all hashes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def load_graph(path: Path) -> nx.DiGraph:
    # The pickle is a trusted local research artifact built by this repository.
    with gzip.open(path, "rb") as handle:
        graph = pickle.load(handle)  # noqa: S301
    if not isinstance(graph, nx.DiGraph):
        raise TypeError(f"Expected networkx.DiGraph, got {type(graph)!r}")
    return graph


def raw_xml_windows_by_doknr(path: Path) -> dict[str, str]:
    """Extract the immutable statute windows keyed by the XML ``doknr``."""
    root = ET.parse(path).getroot()
    windows: dict[str, str] = {}
    for norm in root.findall("norm"):
        doknr = norm.attrib.get("doknr", "")
        text_element = norm.find(".//textdaten/text")
        if not doknr or text_element is None:
            continue
        windows[doknr] = ET.tostring(
            text_element,
            encoding="unicode",
            method="text",
        ).strip()
    return windows


def edge_record(graph: nx.DiGraph, source: str, target: str) -> dict[str, str]:
    data = graph.get_edge_data(source, target, default={})
    return {
        "source": source,
        "target": target,
        "edge_type": str(data.get("edge_type", "reference")),
    }


def topology_record(
    graph: nx.DiGraph,
    nodes: Iterable[str],
    *,
    parent_scc_sha256: str | None = None,
    edge_delta: Mapping[str, Any] | None = None,
    control_kind: str = "native-scc",
) -> dict[str, Any]:
    ordered_nodes = sorted(nodes)
    node_set = set(ordered_nodes)
    edges = sorted(
        (
            edge_record(graph, source, target)
            for source, target in graph.edges()
            if source in node_set and target in node_set
        ),
        key=lambda edge: (edge["source"], edge["target"], edge["edge_type"]),
    )
    hash_payload = {"nodes": ordered_nodes, "edges": edges}
    subgraph = nx.DiGraph()
    subgraph.add_nodes_from(ordered_nodes)
    subgraph.add_edges_from((edge["source"], edge["target"]) for edge in edges)
    return {
        "control_kind": control_kind,
        "nodes": ordered_nodes,
        "edges": edges,
        "node_count": len(ordered_nodes),
        "edge_count": len(edges),
        "sha256": sha256_json(hash_payload),
        "is_strongly_connected": nx.is_strongly_connected(subgraph),
        "is_dag": nx.is_directed_acyclic_graph(subgraph),
        "parent_scc_sha256": parent_scc_sha256,
        "edge_delta": dict(edge_delta or {"removed": [], "added": []}),
    }


def exact_scc_inventory(graph: nx.DiGraph) -> tuple[dict[int, int], dict[int, list[set[str]]]]:
    by_size: dict[int, list[set[str]]] = {}
    for component in nx.strongly_connected_components(graph):
        if len(component) <= 1:
            continue
        by_size.setdefault(len(component), []).append(set(component))
    for components in by_size.values():
        components.sort(key=lambda component: tuple(sorted(component)))
    inventory = {size: len(components) for size, components in sorted(by_size.items())}
    return inventory, by_size


def directed_diameter_anchors(graph: nx.DiGraph, nodes: set[str]) -> dict[str, Any]:
    """Pick a reproducible far-apart seed/witness and a path midpoint bridge."""
    subgraph = graph.subgraph(nodes)
    candidates: list[tuple[int, str, str, list[str]]] = []
    for source in sorted(nodes):
        paths = nx.single_source_shortest_path(subgraph, source)
        for target in sorted(nodes):
            if source == target:
                continue
            path = paths[target]
            candidates.append((len(path) - 1, source, target, path))
    if not candidates:
        raise ValueError("Carrier must have at least three nodes")
    max_distance = max(item[0] for item in candidates)
    # Longest distance first; lexical source/target and lexical shortest path break ties.
    _, seed, witness, path = min(
        (item for item in candidates if item[0] == max_distance),
        key=lambda item: (item[1], item[2], tuple(item[3])),
    )
    if len(path) >= 3:
        bridge = path[len(path) // 2]
    else:
        bridge = next(node for node in sorted(nodes) if node not in {seed, witness})
    if len({seed, bridge, witness}) != 3:
        raise AssertionError("seed/bridge/witness anchors must be distinct")
    return {
        "seed_source_id": seed,
        "bridge_source_id": bridge,
        "witness_source_id": witness,
        "native_shortest_path": path,
        "seed_to_witness_distance": max_distance,
    }


def dfs_preorder(
    graph: nx.DiGraph,
    nodes: set[str],
    root: str,
    preferred_path: Sequence[str],
) -> list[str]:
    """Return a root-reachable DFS order while preserving a preferred path.

    The preferred path is visited before side branches.  Consequently every
    preferred-path edge and every DFS-tree edge points forward in the returned
    order and survives the acyclic forward-edge projection.
    """
    node_set = set(nodes)
    if root not in node_set:
        raise ValueError(f"DAG root {root!r} is outside the carrier")
    if not preferred_path or preferred_path[0] != root:
        raise ValueError("Preferred path must start at the frozen DAG root")
    if len(set(preferred_path)) != len(preferred_path):
        raise ValueError("Preferred path must be simple")
    if not set(preferred_path).issubset(node_set):
        raise ValueError("Preferred path leaves the carrier")
    for source, target in zip(preferred_path, preferred_path[1:]):
        if not graph.has_edge(source, target):
            raise ValueError(f"Preferred path uses missing native edge {source}->{target}")
    preferred_next = {
        source: target for source, target in zip(preferred_path, preferred_path[1:])
    }
    adjacency = {
        node: sorted(
            (target for target in graph.successors(node) if target in node_set),
            key=lambda target: (target != preferred_next.get(node), target),
        )
        for node in node_set
    }
    order: list[str] = []
    seen: set[str] = set()

    def visit(node: str) -> None:
        seen.add(node)
        order.append(node)
        for target in adjacency[node]:
            if target not in seen:
                visit(target)

    visit(root)
    if seen != node_set:
        raise AssertionError("A native SCC should be reachable from its smallest node")
    return order


def make_dag_control(
    graph: nx.DiGraph,
    nodes: set[str],
    parent_hash: str,
    root_source_id: str,
    reference_path: Sequence[str],
) -> nx.DiGraph:
    """Remove feedback edges according to a frozen DFS preorder.

    This is deliberately called a cycle-removed control rather than an identical
    topology match.  It preserves all nodes and original windows, keeps every
    original forward edge, and records every removed edge.
    """
    order = dfs_preorder(graph, nodes, root_source_id, reference_path)
    rank = {node: index for index, node in enumerate(order)}
    dag = nx.DiGraph(name="bgb_matched_dag_control")
    for node in sorted(nodes):
        dag.add_node(node, **dict(graph.nodes[node]))
    for source, target, data in graph.subgraph(nodes).edges(data=True):
        if rank[source] < rank[target]:
            dag.add_edge(source, target, **dict(data))
    if not nx.is_directed_acyclic_graph(dag):
        raise AssertionError("DFS-forward-edge transform must be acyclic")
    reachable = nx.descendants(dag, root_source_id) | {root_source_id}
    if reachable != nodes:
        missing = sorted(nodes - reachable)
        raise AssertionError(f"DAG root cannot reach all carrier nodes: {missing}")
    if any(not dag.has_edge(source, target) for source, target in zip(reference_path, reference_path[1:])):
        raise AssertionError("DAG control dropped an edge from the frozen reference route")
    dag.graph["dfs_preorder"] = order
    dag.graph["parent_scc_sha256"] = parent_hash
    dag.graph["root_source_id"] = root_source_id
    dag.graph["reference_path"] = list(reference_path)
    return dag


@dataclass(frozen=True)
class Fragment:
    source_id: str
    fragment_id: str
    facts: tuple[str, ...] = ()
    rules: tuple[tuple[str, tuple[str, ...], str], ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "facts": list(self.facts),
            "rules": [
                {"rule_id": rule_id, "head": head, "body": list(body)}
                for head, body, rule_id in self.rules
            ],
        }


def closure_naive(fragments: Sequence[Fragment]) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Independent exact LFP executor A: full rule scan until no change."""
    closure: set[str] = set()
    provenance: dict[str, dict[str, Any]] = {}
    rules: list[tuple[str, tuple[str, ...], str, str, str]] = []
    for fragment in fragments:
        for fact in fragment.facts:
            closure.add(fact)
            provenance.setdefault(
                fact,
                {
                    "kind": "fact",
                    "source_id": fragment.source_id,
                    "fragment_id": fragment.fragment_id,
                },
            )
        for head, body, rule_id in fragment.rules:
            rules.append((head, body, rule_id, fragment.source_id, fragment.fragment_id))
    changed = True
    while changed:
        changed = False
        for head, body, rule_id, source_id, fragment_id in rules:
            if head not in closure and all(atom in closure for atom in body):
                closure.add(head)
                provenance[head] = {
                    "kind": "rule",
                    "rule_id": rule_id,
                    "body": list(body),
                    "source_id": source_id,
                    "fragment_id": fragment_id,
                }
                changed = True
    return closure, provenance


def closure_agenda(fragments: Sequence[Fragment]) -> set[str]:
    """Independent exact LFP executor B: indexed agenda/semi-naive propagation."""
    closure: set[str] = set()
    agenda: deque[str] = deque()
    rules: list[tuple[str, tuple[str, ...]]] = []
    waiting: dict[str, set[int]] = {}
    remaining: list[set[str]] = []
    for fragment in fragments:
        for fact in fragment.facts:
            if fact not in closure:
                closure.add(fact)
                agenda.append(fact)
        for head, body, _ in fragment.rules:
            index = len(rules)
            rules.append((head, body))
            body_set = set(body)
            remaining.append(body_set)
            for atom in body_set:
                waiting.setdefault(atom, set()).add(index)
    # Account for facts before starting propagation and fire empty-body rules.
    for index, (_, body) in enumerate(rules):
        remaining[index].difference_update(closure)
        if not body and rules[index][0] not in closure:
            closure.add(rules[index][0])
            agenda.append(rules[index][0])
    while agenda:
        atom = agenda.popleft()
        for index in sorted(waiting.get(atom, ())):
            remaining[index].discard(atom)
            head, _ = rules[index]
            if not remaining[index] and head not in closure:
                closure.add(head)
                agenda.append(head)
    return closure


def rule_dependency_is_acyclic(fragments: Sequence[Fragment]) -> bool:
    dependencies = nx.DiGraph()
    for fragment in fragments:
        for head, body, _ in fragment.rules:
            dependencies.add_node(head)
            for atom in body:
                dependencies.add_edge(atom, head)
    return nx.is_directed_acyclic_graph(dependencies)


def proof_tree(atom: str, provenance: Mapping[str, Mapping[str, Any]], seen: set[str] | None = None) -> dict[str, Any]:
    seen = set(seen or ())
    if atom in seen:
        raise AssertionError(f"Cyclic provenance while proving {atom}")
    item = dict(provenance[atom])
    node: dict[str, Any] = {"atom": atom, **item}
    if item["kind"] == "rule":
        node["premises"] = [proof_tree(body_atom, provenance, seen | {atom}) for body_atom in item["body"]]
    return node


def proof_source_ids(proof: Mapping[str, Any] | None) -> list[str]:
    if proof is None:
        return []
    result = {str(proof["source_id"])} if proof.get("source_id") else set()
    for premise in proof.get("premises", []):
        result.update(proof_source_ids(premise))
    return sorted(result)


def minimum_source_covers(fragments: Sequence[Fragment], query_atom: str) -> list[list[str]]:
    source_ids = sorted({fragment.source_id for fragment in fragments})
    for width in range(len(source_ids) + 1):
        covers: list[list[str]] = []
        for subset_tuple in itertools.combinations(source_ids, width):
            subset = set(subset_tuple)
            enabled = [fragment for fragment in fragments if fragment.source_id in subset]
            closure, _ = closure_naive(enabled)
            if query_atom in closure:
                covers.append(list(subset_tuple))
        if covers:
            return covers
    return []


def atom_names(carrier_id: str) -> dict[str, str]:
    token = carrier_id.replace("-", "_")
    return {
        "seed": f"seed_ready({token})",
        "bridge": f"bridge_ready({token})",
        "query": f"review_released({token})",
        "decoy_seed": f"seed_ready({token}__parallel)",
        "decoy_bridge": f"bridge_ready({token}__parallel)",
        "decoy_query": f"review_released({token}__parallel)",
    }


def controlled_note(marker: str, body: str) -> str:
    return f"[{marker}]\n{body.strip()}\n[/{marker}]"


def note_bodies(
    carrier_id: str,
    anchors: Mapping[str, str],
    headings: Mapping[str, str],
    condition: str,
    atoms: Mapping[str, str],
) -> dict[str, str]:
    seed_heading = headings[anchors["seed_source_id"]]
    bridge_heading = headings[anchors["bridge_source_id"]]
    witness_heading = headings[anchors["witness_source_id"]]
    if condition in {"Productive", "Matched-DAG", "Broken"}:
        result = {
            "seed": (
                f"Kontrollierter Testvermerk {carrier_id}: Der Ausgangsstatus ist in {seed_heading} "
                f"für genau diesen Testfall gesetzt (symbolisch: {atoms['seed']}). Dieser Vermerk "
                "allein bestätigt die Gesamtfreigabe ausdrücklich nicht."
            ),
            "witness": (
                f"Kontrollierter Testvermerk {carrier_id}: Nur wenn der Zwischenstatus aus "
                f"{bridge_heading} für denselben Testfall gilt, wird in {witness_heading} die "
                f"Gesamtfreigabe festgestellt (symbolisch: {atoms['query']} <- {atoms['bridge']}). "
                "Dieser Vermerk setzt den Zwischenstatus nicht selbst."
            ),
        }
        if condition != "Broken":
            result["bridge"] = (
                f"Kontrollierter Testvermerk {carrier_id}: Nur wenn der Ausgangsstatus aus "
                f"{seed_heading} für denselben Testfall gilt, wird hier der Zwischenstatus "
                f"festgestellt (symbolisch: {atoms['bridge']} <- {atoms['seed']}). Dieser "
                "Vermerk setzt den Ausgangsstatus nicht selbst."
            )
        return result
    if condition == "Decoy":
        return {
            "seed": (
                f"Kontrollierter Parallelvermerk zu {carrier_id}: Der Ausgangsstatus gehört nur "
                f"zum ausdrücklich getrennten Parallelfall (symbolisch: {atoms['decoy_seed']}); "
                "er gilt nicht für die gestellte Prüfakte."
            ),
            "bridge": (
                f"Kontrollierter Parallelvermerk zu {carrier_id}: Für den getrennten Parallelfall "
                f"gilt {atoms['decoy_bridge']} <- {atoms['decoy_seed']}. Eine Übertragung auf die "
                "gestellte Prüfakte ist ausgeschlossen."
            ),
            "witness": (
                f"Kontrollierter Parallelvermerk zu {carrier_id}: Nur im getrennten Parallelfall "
                f"gilt {atoms['decoy_query']} <- {atoms['decoy_bridge']}. Dies ist keine Freigabe "
                "der gestellten Prüfakte."
            ),
        }
    if condition == "Clean":
        return {}
    raise ValueError(f"Unknown condition: {condition}")


def formal_fragments(
    condition: str,
    anchors: Mapping[str, str],
    atoms: Mapping[str, str],
) -> tuple[list[Fragment], list[dict[str, Any]]]:
    seed_id = anchors["seed_source_id"]
    bridge_id = anchors["bridge_source_id"]
    witness_id = anchors["witness_source_id"]
    if condition in {"Productive", "Matched-DAG"}:
        fragments = [
            Fragment(seed_id, "seed", facts=(atoms["seed"],)),
            Fragment(
                bridge_id,
                "bridge",
                rules=((atoms["bridge"], (atoms["seed"],), "r_seed_to_bridge"),),
            ),
            Fragment(
                witness_id,
                "witness",
                rules=((atoms["query"], (atoms["bridge"],), "r_bridge_to_query"),),
            ),
        ]
        intended = [fragment.as_json() for fragment in fragments]
        return fragments, intended
    if condition == "Decoy":
        fragments = [
            Fragment(seed_id, "seed", facts=(atoms["decoy_seed"],)),
            Fragment(
                bridge_id,
                "bridge",
                rules=((atoms["decoy_bridge"], (atoms["decoy_seed"],), "r_decoy_seed_to_bridge"),),
            ),
            Fragment(
                witness_id,
                "witness",
                rules=((atoms["decoy_query"], (atoms["decoy_bridge"],), "r_decoy_bridge_to_query"),),
            ),
        ]
        return fragments, [fragment.as_json() for fragment in fragments]
    if condition == "Broken":
        fragments = [
            Fragment(seed_id, "seed", facts=(atoms["seed"],)),
            Fragment(
                witness_id,
                "witness",
                rules=((atoms["query"], (atoms["bridge"],), "r_bridge_to_query"),),
            ),
        ]
        intended = [
            fragments[0].as_json(),
            {
                "facts": [],
                "rules": [
                    {
                        "rule_id": "r_seed_to_bridge",
                        "head": atoms["bridge"],
                        "body": [atoms["seed"]],
                    }
                ],
            },
            fragments[1].as_json(),
        ]
        return fragments, intended
    if condition == "Clean":
        return [], []
    raise ValueError(f"Unknown condition: {condition}")


def build_patch_log(
    condition: str,
    marker: str,
    anchors: Mapping[str, str],
    notes: Mapping[str, str],
    fragments: Sequence[Fragment],
    intended_formal: Sequence[Mapping[str, Any]],
    original_by_node: Mapping[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    role_to_source = {
        "seed": anchors["seed_source_id"],
        "bridge": anchors["bridge_source_id"],
        "witness": anchors["witness_source_id"],
    }
    fragment_by_role = {fragment.fragment_id: fragment for fragment in fragments}
    intended_by_role = {
        role: dict(formal)
        for role, formal in zip(("seed", "bridge", "witness"), intended_formal, strict=False)
    }
    rendered = dict(original_by_node)
    patches: list[dict[str, Any]] = []
    if condition == "Clean":
        return patches, rendered
    for role in ("seed", "bridge", "witness"):
        source_id = role_to_source[role]
        original = original_by_node[source_id]
        fragment = fragment_by_role.get(role)
        note_body = notes.get(role)
        if condition == "Broken" and role == "bridge":
            patch = {
                "patch_id": f"{condition.lower()}-{role}",
                "source_id": source_id,
                "role": role,
                "operation": "omit_noop",
                "append_position": "end",
                "separator": "\\n\\n",
                "marker": marker,
                "original_text_sha256": sha256_text(original),
                "original_char_count": len(original),
                "appended_note": "",
                "note_sha256": sha256_text(""),
                "rendered_text_sha256": sha256_text(original),
                "formal_injection": {"facts": [], "rules": []},
                "intended_but_omitted_formal_injection": intended_by_role[role],
                "reason": "bridge deliberately omitted; original BGB text is untouched",
            }
            patches.append(patch)
            continue
        if note_body is None or fragment is None:
            raise AssertionError(f"Missing {role} note/fragment for {condition}")
        delimited = controlled_note(marker, note_body)
        rendered_text = f"{original}\n\n{delimited}"
        rendered[source_id] = rendered_text
        patches.append(
            {
                "patch_id": f"{condition.lower()}-{role}",
                "source_id": source_id,
                "role": role,
                "operation": "append",
                "append_position": "end",
                "separator": "\\n\\n",
                "marker": marker,
                "original_text_sha256": sha256_text(original),
                "original_char_count": len(original),
                "appended_note": delimited,
                "note_sha256": sha256_text(delimited),
                "rendered_text_sha256": sha256_text(rendered_text),
                "formal_injection": fragment.as_json(),
                "intended_but_omitted_formal_injection": None,
                "reason": "append-only controlled symbolic fragment",
            }
        )
    return patches, rendered


def source_records(
    graph: nx.DiGraph,
    nodes: Iterable[str],
    rendered_by_node: Mapping[str, str],
    patches: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    patch_ids_by_source: dict[str, list[str]] = {}
    for patch in patches:
        patch_ids_by_source.setdefault(str(patch["source_id"]), []).append(str(patch["patch_id"]))
    records = []
    for node in sorted(nodes):
        data = graph.nodes[node]
        original = str(data.get("text", ""))
        rendered = rendered_by_node[node]
        records.append(
            {
                "source_id": node,
                "heading": str(data.get("heading", node)),
                "section_number": str(data.get("section_number", "")),
                "document_key": str(data.get("key", "")),
                "doknr": str(data.get("doknr", "")),
                "raw_xml_locator": {
                    "doknr": str(data.get("doknr", "")),
                    "element": "norm/textdaten/text",
                },
                "original_text": original,
                "rendered_text": rendered,
                "original_text_sha256": sha256_text(original),
                "rendered_text_sha256": sha256_text(rendered),
                "patch_ids": sorted(patch_ids_by_source.get(node, [])),
            }
        )
    return records


def build_oracle(
    fragments: Sequence[Fragment],
    query_atom: str,
    expected_label: str,
    required_sources: Sequence[str],
) -> dict[str, Any]:
    closure_a, provenance = closure_naive(fragments)
    closure_b = closure_agenda(fragments)
    entailed = query_atom in closure_a
    actual_label = LABEL_ENTAILED if entailed else LABEL_UNKNOWN
    proof = proof_tree(query_atom, provenance) if entailed else None
    covers = minimum_source_covers(fragments, query_atom)
    no_fact_closure, _ = closure_naive(
        [Fragment(fragment.source_id, fragment.fragment_id, rules=fragment.rules) for fragment in fragments]
    )
    leave_one_out = {}
    for source_id in required_sources:
        reduced = [fragment for fragment in fragments if fragment.source_id != source_id]
        reduced_closure, _ = closure_naive(reduced)
        leave_one_out[source_id] = query_atom not in reduced_closure
    return {
        "actual_label": actual_label,
        "closure": sorted(closure_a),
        "proof": proof,
        "proof_source_ids": proof_source_ids(proof),
        "minimum_source_cover": covers[0] if covers else None,
        "all_minimum_source_covers": covers,
        "leave_one_required_source_out_unknown": leave_one_out,
        "gates": {
            "expected_label_matches": actual_label == expected_label,
            "independent_closures_equal": closure_a == closure_b,
            "rule_dependency_is_acyclic": rule_dependency_is_acyclic(fragments),
            "query_not_entailed_without_injected_facts": query_atom not in no_fact_closure,
            "all_required_leave_one_out_unknown": all(leave_one_out.values()),
        },
    }


def case_ids(carrier_size: int, native_hash: str, condition: str) -> tuple[str, str]:
    carrier_id = f"bgb-scc-{carrier_size:02d}-{native_hash[:10]}"
    condition_slug = condition.lower().replace("-", "_")
    return carrier_id, f"{carrier_id}--{condition_slug}"


def expected_label(condition: str) -> str:
    return LABEL_ENTAILED if condition in {"Productive", "Matched-DAG"} else LABEL_UNKNOWN


def build_case(
    graph: nx.DiGraph,
    nodes: set[str],
    anchors: Mapping[str, Any],
    native_topology: Mapping[str, Any],
    dag_graph: nx.DiGraph,
    dag_topology: Mapping[str, Any],
    carrier_tier: str,
    condition: str,
    marker: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    size = len(nodes)
    carrier_id, case_id = case_ids(size, str(native_topology["sha256"]), condition)
    headings = {node: str(graph.nodes[node].get("heading", node)) for node in nodes}
    atoms = atom_names(carrier_id)
    notes = note_bodies(carrier_id, anchors, headings, condition, atoms)
    fragments, intended_formal = formal_fragments(condition, anchors, atoms)
    original_by_node = {node: str(graph.nodes[node].get("text", "")) for node in nodes}
    patches, rendered_by_node = build_patch_log(
        condition,
        marker,
        anchors,
        notes,
        fragments,
        intended_formal,
        original_by_node,
    )
    topology = dag_topology if condition == "Matched-DAG" else native_topology
    topology_graph = dag_graph if condition == "Matched-DAG" else graph
    sources = source_records(graph, nodes, rendered_by_node, patches)
    required_sources = (
        [
            anchors["seed_source_id"],
            anchors["bridge_source_id"],
            anchors["witness_source_id"],
        ]
        if condition in {"Productive", "Matched-DAG"}
        else []
    )
    declared_label = expected_label(condition)
    oracle = build_oracle(fragments, atoms["query"], declared_label, required_sources)
    root_source_id = str(anchors["seed_source_id"])
    reference_route = [str(node) for node in anchors["native_shortest_path"]]
    case_subgraph = topology_graph.subgraph(nodes)
    root_reachable_sources = sorted(nx.descendants(case_subgraph, root_source_id) | {root_source_id})
    root_reachable_set = set(root_reachable_sources)
    navigation_target_ids = [
        str(anchors["seed_source_id"]),
        str(anchors["bridge_source_id"]),
        str(anchors["witness_source_id"]),
    ]
    reference_route_edges_exist = all(
        case_subgraph.has_edge(source, target)
        for source, target in zip(reference_route, reference_route[1:])
    )
    reachable_fragments = [
        fragment for fragment in fragments if fragment.source_id in root_reachable_set
    ]
    reachable_closure, _ = closure_naive(reachable_fragments)
    reachable_label = LABEL_ENTAILED if atoms["query"] in reachable_closure else LABEL_UNKNOWN
    default_action_budget = 2 * len(nodes) + 2
    route_move_cost = max(0, len(reference_route) - 1)
    route_read_cost = len(navigation_target_ids)
    route_total_action_cost = route_move_cost + route_read_cost
    navigation_contract = {
        "root_source_id": root_source_id,
        "root_reachable_source_ids": root_reachable_sources,
        "unreachable_source_ids": sorted(nodes - root_reachable_set),
        "navigation_target_source_ids": navigation_target_ids,
        "required_proof_source_ids": list(required_sources),
        "reference_route": reference_route,
        "reference_route_move_cost": route_move_cost,
        "reference_route_read_cost": route_read_cost,
        "reference_route_total_action_cost": route_total_action_cost,
        "default_action_budget": default_action_budget,
        "reachable_exact_lfp_label": reachable_label,
    }
    oracle["gates"].update(
        {
            "root_reaches_all_sources": root_reachable_set == nodes,
            "root_reaches_all_navigation_targets": set(navigation_target_ids).issubset(root_reachable_set),
            "root_reaches_all_required_proof_sources": set(required_sources).issubset(root_reachable_set),
            "reference_route_starts_at_root": bool(reference_route) and reference_route[0] == root_source_id,
            "reference_route_edges_exist": reference_route_edges_exist,
            "reference_route_covers_navigation_targets": set(navigation_target_ids).issubset(reference_route),
            "reference_route_action_cost_within_default_budget": route_total_action_cost <= default_action_budget,
            "reachable_exact_lfp_label_matches_expected": reachable_label == declared_label,
        }
    )
    original_window_set_hash = sha256_json(
        [{"source_id": source["source_id"], "sha256": source["original_text_sha256"]} for source in sources]
    )
    public_case = {
        "schema_version": PUBLIC_SCHEMA,
        "case_id": case_id,
        "carrier_id": carrier_id,
        "carrier_size": size,
        "carrier_tier": carrier_tier,
        "condition": condition,
        "query": {
            "text": (
                "Ist der kontrollierte Prüfstatus für diese Akte durch die bereitgestellten "
                "Quellen vollständig freigegeben? Antworten Sie nur mit Entailed oder PR-Unknown "
                "und nennen Sie die verwendeten Quellen."
            ),
            "atom": atoms["query"],
            "labels": [LABEL_ENTAILED, LABEL_UNKNOWN],
        },
        "topology": dict(topology),
        "sources": sources,
        "source_order": sorted(nodes),
        "root_source_id": root_source_id,
        "original_window_set_sha256": original_window_set_hash,
        "controlled_note_marker": marker,
        "public_notice": (
            "Model-visible controlled benchmark case. Gold labels and formal programs are held "
            "in the evaluator-only sidecar."
        ),
    }
    gold_sidecar = {
        "schema_version": GOLD_SCHEMA,
        "case_id": case_id,
        "carrier_id": carrier_id,
        "condition": condition,
        "expected_label": declared_label,
        "query_atom": atoms["query"],
        "anchors": anchors,
        "injected_patches": patches,
        "required_injected_source_ids": required_sources,
        "recommended_smoke_execution_order": [
            anchors["seed_source_id"],
            anchors["bridge_source_id"],
            anchors["witness_source_id"],
        ],
        "navigation_contract": navigation_contract,
        "formal_program": {
            "semantics": "positive function-free Horn least fixed point",
            "fragments": [
                {
                    "source_id": fragment.source_id,
                    "fragment_id": fragment.fragment_id,
                    **fragment.as_json(),
                }
                for fragment in fragments
            ],
        },
        "oracle": oracle,
        "audit": {
            "native_topology_sha256": native_topology["sha256"],
            "case_topology_sha256": topology["sha256"],
            "original_window_set_sha256": original_window_set_hash,
            "source_text_is_from_native_carrier": all(
                source["original_text"] == str(graph.nodes[source["source_id"]].get("text", ""))
                for source in sources
            ),
            "case_topology_is_dag": nx.is_directed_acyclic_graph(topology_graph.subgraph(nodes)),
            "root_reachable_source_ids": root_reachable_sources,
            "reachable_exact_lfp_label": reachable_label,
        },
    }
    return public_case, gold_sidecar


def finalize_cross_condition_gates(
    public_cases: Sequence[dict[str, Any]],
    sidecars: Sequence[dict[str, Any]],
) -> None:
    public_by_condition = {case["condition"]: case for case in public_cases}
    native_conditions = ["Productive", "Decoy", "Broken", "Clean"]
    native_hashes = {public_by_condition[name]["topology"]["sha256"] for name in native_conditions}
    original_hashes = {
        public_by_condition[name]["original_window_set_sha256"] for name in native_conditions
    }
    dag_case = public_by_condition["Matched-DAG"]
    cross_gates = {
        "pdbc_topology_hashes_equal": len(native_hashes) == 1,
        "pdbc_original_window_hashes_equal": len(original_hashes) == 1,
        "matched_dag_is_acyclic": bool(dag_case["topology"]["is_dag"]),
        "matched_dag_topology_hash_is_separate": dag_case["topology"]["sha256"] not in native_hashes,
        "matched_dag_parent_hash_matches_native": dag_case["topology"]["parent_scc_sha256"] in native_hashes,
    }
    for sidecar in sidecars:
        sidecar["oracle"]["gates"].update(cross_gates)
        sidecar["oracle"]["all_gates_pass"] = all(sidecar["oracle"]["gates"].values())


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(canonical_json(record))
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config = load_json(args.config.resolve())
    graph_path = resolve_repo_path(config["inputs"]["graph"])
    xml_path = resolve_repo_path(config["inputs"]["raw_xml"])
    output_dir = resolve_repo_path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = load_graph(graph_path)
    raw_xml_windows = raw_xml_windows_by_doknr(xml_path)
    inventory, by_size = exact_scc_inventory(graph)
    smoke_sizes = [int(value) for value in config["carrier_sizes"]["smoke"]]
    pressure_sizes = [int(value) for value in config["carrier_sizes"]["pressure_only"]]
    target_sizes = smoke_sizes + pressure_sizes
    missing = [size for size in target_sizes if size not in by_size]
    if missing:
        raise RuntimeError(f"Native BGB graph lacks requested exact SCC sizes: {missing}")

    all_public: list[dict[str, Any]] = []
    all_sidecars: list[dict[str, Any]] = []
    carrier_manifest: list[dict[str, Any]] = []
    selected_windows_match_raw_xml = True
    for size in target_sizes:
        nodes = by_size[size][0]
        carrier_windows_match_raw_xml = all(
            raw_xml_windows.get(str(graph.nodes[node].get("doknr", "")))
            == str(graph.nodes[node].get("text", ""))
            for node in nodes
        )
        if not carrier_windows_match_raw_xml:
            raise AssertionError(f"Selected size-{size} carrier does not match frozen raw XML")
        selected_windows_match_raw_xml &= carrier_windows_match_raw_xml
        native = topology_record(graph, nodes)
        anchors = directed_diameter_anchors(graph, nodes)
        dag_graph = make_dag_control(
            graph,
            nodes,
            str(native["sha256"]),
            str(anchors["seed_source_id"]),
            [str(node) for node in anchors["native_shortest_path"]],
        )
        native_edge_pairs = {(edge["source"], edge["target"]) for edge in native["edges"]}
        dag_edge_pairs = set(dag_graph.edges())
        removed = [
            {"source": source, "target": target}
            for source, target in sorted(native_edge_pairs - dag_edge_pairs)
        ]
        dag = topology_record(
            dag_graph,
            nodes,
            parent_scc_sha256=str(native["sha256"]),
            edge_delta={"removed": removed, "added": []},
            control_kind="cycle-removed-dag",
        )
        tier = "smoke" if size in smoke_sizes else "pressure-only"
        carrier_public: list[dict[str, Any]] = []
        carrier_sidecars: list[dict[str, Any]] = []
        for condition in config["conditions"]:
            public_case, sidecar = build_case(
                graph,
                nodes,
                anchors,
                native,
                dag_graph,
                dag,
                tier,
                str(condition),
                str(config["controlled_note_marker"]),
            )
            carrier_public.append(public_case)
            carrier_sidecars.append(sidecar)
        finalize_cross_condition_gates(carrier_public, carrier_sidecars)
        all_public.extend(carrier_public)
        all_sidecars.extend(carrier_sidecars)
        carrier_id = carrier_public[0]["carrier_id"]
        carrier_manifest.append(
            {
                "carrier_id": carrier_id,
                "size": size,
                "tier": tier,
                "nodes": sorted(nodes),
                "native_edge_count": native["edge_count"],
                "native_topology_sha256": native["sha256"],
                "matched_dag_edge_count": dag["edge_count"],
                "matched_dag_topology_sha256": dag["sha256"],
                "matched_dag_removed_edge_count": len(removed),
                "anchor_selection": anchors,
                "dag_navigation_contract": carrier_sidecars[-1]["navigation_contract"],
                "all_windows_exact_raw_xml_match": carrier_windows_match_raw_xml,
                "case_ids": [case["case_id"] for case in carrier_public],
            }
        )

    combined = [
        {
            "schema_version": COMBINED_SCHEMA,
            "public_case": public,
            "evaluator_sidecar": sidecar,
        }
        for public, sidecar in zip(all_public, all_sidecars, strict=True)
    ]
    public_path = output_dir / "public_cases.jsonl"
    sidecar_path = output_dir / "gold_sidecar.jsonl"
    combined_path = output_dir / "cases.jsonl"
    write_jsonl(public_path, all_public)
    write_jsonl(sidecar_path, all_sidecars)
    write_jsonl(combined_path, combined)

    failed_case_ids = [
        sidecar["case_id"] for sidecar in all_sidecars if not sidecar["oracle"]["all_gates_pass"]
    ]
    condition_counts = {
        condition: sum(case["condition"] == condition for case in all_public)
        for condition in config["conditions"]
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "status": "PASS" if not failed_case_ids else "FAIL",
        "builder": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        "config": config,
        "input_artifacts": {
            "graph": {
                "path": str(graph_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(graph_path),
                "node_count": graph.number_of_nodes(),
                "edge_count": graph.number_of_edges(),
            },
            "raw_xml": {
                "path": str(xml_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(xml_path),
                "byte_count": xml_path.stat().st_size,
            },
        },
        "native_scc_inventory": {str(size): count for size, count in inventory.items()},
        "requested_exact_sizes": target_sizes,
        "unavailable_requested_ladder_sizes": [12, 16, 20],
        "unavailable_size_note": (
            "The frozen 2019 BGB graph has no native SCC of size 12, 16, or 20; none were "
            "fabricated. Native size 11 and 25 carriers are retained as pressure-only cases."
        ),
        "carriers": carrier_manifest,
        "case_count": len(all_public),
        "smoke_case_count": sum(case["carrier_tier"] == "smoke" for case in all_public),
        "pressure_case_count": sum(case["carrier_tier"] == "pressure-only" for case in all_public),
        "condition_counts": condition_counts,
        "failed_case_ids": failed_case_ids,
        "global_gates": {
            "all_case_gates_pass": not failed_case_ids,
            "all_requested_native_sizes_found": not missing,
            "public_gold_record_counts_equal": len(all_public) == len(all_sidecars),
            "public_case_ids_unique": len({case["case_id"] for case in all_public}) == len(all_public),
            "every_original_window_nonempty": all(
                source["original_text"]
                for case in all_public
                for source in case["sources"]
            ),
            "every_selected_window_exact_raw_xml_match": selected_windows_match_raw_xml,
        },
        "outputs": {},
        "scope_limitations": [
            "Controlled injection establishes mechanism behavior, not the natural prevalence of such evidence chains.",
            "Matched-DAG removes recorded feedback edges and therefore is a separate physical-topology control, not the same topology hash.",
            "The exact LFP oracle operates only on injected positive-Horn fragments; original German legal prose is not converted into a gold logic program.",
            "Sizes 11 and 25 are pressure-only until the 3/5/7/9 end-to-end smoke passes.",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    # Hash JSONL artifacts before writing the manifest itself.
    manifest["outputs"] = {
        path.name: {"sha256": sha256_file(path), "byte_count": path.stat().st_size}
        for path in (public_path, sidecar_path, combined_path)
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"status={manifest['status']}")
    print(f"carriers={len(carrier_manifest)} cases={len(all_public)}")
    print(f"smoke_cases={manifest['smoke_case_count']} pressure_cases={manifest['pressure_case_count']}")
    for carrier in carrier_manifest:
        print(
            "size={size} tier={tier} nodes={nodes} native_edges={native_edge_count} "
            "dag_edges={matched_dag_edge_count} removed={matched_dag_removed_edge_count}".format(**carrier)
        )
    print(f"manifest={manifest_path}")
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
