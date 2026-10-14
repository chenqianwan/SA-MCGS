#!/usr/bin/env python3
"""Reproduce the SIGNOR/OpenBEL/AOP-Wiki/OmniPath feedback audit.

The raw snapshots live under ``raw/biology`` and are intentionally ignored by
git.  This script verifies their pinned hashes, recomputes compact graph and
evidence statistics, and writes the tracked ``biology_feedback_audit.json``.

SCCs reported here are entity or typed-state SCCs.  They are deliberately not
described as predicate-dependency SCCs.  Likewise, reachability/least-fixed-
point closure is a benchmark semantics derived by us, not a biological truth
asserted by any of the four publishers.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Hashable, Sequence

import networkx as nx


AUDIT_DATE = "2026-08-18"

DATASETS = {
    "signor": {
        "relative_path": "signor/Apr2026_release.txt",
        "snapshot": "Apr2026",
        "retrieved_on": "2026-08-16",
        "url": "https://signor.uniroma2.it/releases/Apr2026_release.txt",
        "expected_sha256": "3ebe96c2d19f2cf7cf92614844366346436c82d79dde67c8d7a5ddfda0a6bd4c",
        "license": "CC BY 4.0",
        "license_url": "https://signor.uniroma2.it/about/",
        "primary_source": "https://academic.oup.com/nar/article/54/D1/D682/8324960",
        "url_is_immutable_snapshot": True,
    },
    "openbel": {
        "relative_path": "openbel/large_corpus.xbel.gz",
        "snapshot": "20150611 at repository commit 3fab82d7886fb4eb251ca22f1d02b74831b141cd",
        "retrieved_on": "2026-08-18",
        "url": (
            "https://raw.githubusercontent.com/OpenBEL/"
            "openbel-framework-resources/"
            "3fab82d7886fb4eb251ca22f1d02b74831b141cd/"
            "knowledge/large_corpus.xbel.gz"
        ),
        "expected_sha256": "38e9cf33b2bfcc87c79c09d33a676882de68a05a8695f411ba3710a6fc753e66",
        "license": "CC BY-NC-SA 3.0 (corpus header; not the repository software license)",
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/3.0/",
        "primary_source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4222496/",
        "url_is_immutable_snapshot": True,
    },
    "aop_wiki": {
        "relative_path": "aop_wiki/aop-wiki-xml-2026-07-01.gz",
        "snapshot": "2026-07-01 quarterly release",
        "retrieved_on": "2026-08-18",
        "url": "https://aopwiki.org/downloads/aop-wiki-xml-2026-07-01.gz",
        "expected_sha256": "24ad8bb09914f57128ad623fa1ca6b80d31b871b781a5f1346e4fc793c4a7aa4",
        "license": "Per-page: BY-SA by default; filter All rights reserved AOP pages",
        "license_url": "https://aopwiki.org/handbooks/5",
        "primary_source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC6010347/",
        "url_is_immutable_snapshot": True,
    },
    "omnipath": {
        "relative_path": "omnipath/omnipath-2026-08-18.tsv",
        "snapshot": "API response captured 2026-08-18",
        "retrieved_on": "2026-08-18",
        "url": (
            "https://omnipathdb.org/interactions?datasets=omnipath"
            "&organisms=9606&genesymbols=yes"
            "&fields=sources,references,curation_effort,evidences,extra_attrs"
            "&license=academic"
        ),
        "expected_sha256": "1964a7bd6f6212efecf0c8d37d512d47a41db958e87b3c71dd2a4cae3388b494",
        "license": "No aggregate license; each upstream resource retains its own license",
        "license_url": "https://omnipathdb.org/info",
        "primary_source": "https://academic.oup.com/nar/article/54/D1/D652/8326458",
        "url_is_immutable_snapshot": False,
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "LFP-MCGS-dataset-audit/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    partial.replace(destination)


def prepare_files(
    raw_root: Path, *, download_missing: bool, allow_hash_mismatch: bool
) -> tuple[dict[str, Path], dict[str, dict]]:
    audit_dir = Path(__file__).resolve().parent
    paths: dict[str, Path] = {}
    source_metadata: dict[str, dict] = {}
    for name, spec in DATASETS.items():
        path = raw_root / spec["relative_path"]
        if not path.exists():
            if not download_missing:
                raise FileNotFoundError(
                    f"Missing {path}. Re-run with --download-missing or place the pinned snapshot there."
                )
            download(spec["url"], path)
        actual_hash = sha256_file(path)
        if actual_hash != spec["expected_sha256"] and not allow_hash_mismatch:
            mutability_hint = (
                " The source is a live API, so retrieve the archived local snapshot or explicitly "
                "use --allow-hash-mismatch to audit a new snapshot."
                if not spec["url_is_immutable_snapshot"]
                else ""
            )
            raise ValueError(
                f"SHA256 mismatch for {name}: expected {spec['expected_sha256']}, "
                f"got {actual_hash}.{mutability_hint}"
            )
        paths[name] = path
        try:
            displayed_path = path.resolve().relative_to(audit_dir).as_posix()
        except ValueError:
            displayed_path = path.resolve().as_posix()
        source_metadata[name] = {
            "snapshot": spec["snapshot"],
            "retrieved_on": spec["retrieved_on"],
            "download_url": spec["url"],
            "url_is_immutable_snapshot": spec["url_is_immutable_snapshot"],
            "local_raw_file": displayed_path,
            "bytes": path.stat().st_size,
            "sha256": actual_hash,
            "expected_sha256": spec["expected_sha256"],
            "hash_matches_pinned_snapshot": actual_hash == spec["expected_sha256"],
            "license": spec["license"],
            "license_url": spec["license_url"],
            "primary_source": spec["primary_source"],
        }
    return paths, source_metadata


def graph_profile(edges: Sequence[tuple[Hashable, Hashable]]) -> dict:
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    components = [
        component
        for component in nx.strongly_connected_components(graph)
        if len(component) > 1
    ]
    component_of = {
        node: component_id
        for component_id, component in enumerate(components)
        for node in component
    }
    internal_records = sum(
        source in component_of
        and target in component_of
        and component_of[source] == component_of[target]
        for source, target in edges
    )
    sizes = sorted((len(component) for component in components), reverse=True)
    return {
        "records": len(edges),
        "nodes": graph.number_of_nodes(),
        "unique_directed_edges": graph.number_of_edges(),
        "nontrivial_sccs": len(components),
        "largest_scc": sizes[0] if sizes else 0,
        "largest_sccs": sizes[:10],
        "cyclic_nodes": len(component_of),
        "records_inside_scc": internal_records,
    }


def grouped_graph_profile(
    records: Sequence[dict], context_key: Callable[[dict], Hashable]
) -> dict:
    groups: dict[Hashable, list[tuple[Hashable, Hashable]]] = defaultdict(list)
    for record in records:
        groups[context_key(record)].append((record["source"], record["target"]))

    sizes: list[int] = []
    groups_with_scc = 0
    cyclic_nodes = 0
    internal_records = 0
    for edges in groups.values():
        profile = graph_profile(edges)
        if profile["nontrivial_sccs"]:
            groups_with_scc += 1
        sizes.extend(profile["largest_sccs"] if profile["nontrivial_sccs"] <= 10 else [])
        # Recompute all sizes when a group could contain more than ten SCCs.
        graph = nx.DiGraph(edges)
        all_components = [
            component
            for component in nx.strongly_connected_components(graph)
            if len(component) > 1
        ]
        if len(all_components) > 10:
            del sizes[-len(profile["largest_sccs"]) :]
            sizes.extend(len(component) for component in all_components)
        cyclic_nodes += profile["cyclic_nodes"]
        internal_records += profile["records_inside_scc"]

    sizes.sort(reverse=True)
    return {
        "records": len(records),
        "context_groups": len(groups),
        "groups_with_nontrivial_scc": groups_with_scc,
        "nontrivial_sccs": len(sizes),
        "largest_scc": sizes[0] if sizes else 0,
        "largest_sccs": sizes[:10],
        "cyclic_nodes_counted_within_context": cyclic_nodes,
        "records_inside_scc": internal_records,
    }


def shared_value(
    positive: Sequence[dict], negative: Sequence[dict], key: Callable[[dict], Hashable]
) -> bool:
    positive_values = {value for row in positive if (value := key(row))}
    negative_values = {value for row in negative if (value := key(row))}
    return bool(positive_values & negative_values)


def opposite_sign_audit(
    records: Sequence[dict], *, context_fields: Sequence[str], detailed_fields: Sequence[str]
) -> dict:
    by_pair: dict[tuple[Hashable, Hashable], dict[str, list[dict]]] = defaultdict(
        lambda: {"+": [], "-": []}
    )
    for record in records:
        by_pair[(record["source"], record["target"])][record["sign"]].append(record)
    collisions = [bucket for bucket in by_pair.values() if bucket["+"] and bucket["-"]]

    def exact_context(row: dict) -> tuple:
        return tuple(row[field] for field in context_fields)

    def detailed_context(row: dict) -> tuple | None:
        context = exact_context(row)
        return context if any(row[field] for field in detailed_fields) else None

    return {
        "ordered_pairs_with_both_signs": len(collisions),
        "pairs_sharing_exact_context": sum(
            shared_value(bucket["+"], bucket["-"], exact_context) for bucket in collisions
        ),
        "pairs_sharing_nonempty_detailed_context": sum(
            shared_value(bucket["+"], bucket["-"], detailed_context)
            and any(detailed_context(row) is not None for row in bucket["+"] + bucket["-"])
            for bucket in collisions
        ),
        "pairs_sharing_publication": sum(
            shared_value(bucket["+"], bucket["-"], lambda row: row["publication"])
            and any(row["publication"] for row in bucket["+"] + bucket["-"])
            for bucket in collisions
        ),
        "pairs_sharing_exact_evidence": sum(
            shared_value(bucket["+"], bucket["-"], lambda row: row["evidence"])
            and any(row["evidence"] for row in bucket["+"] + bucket["-"])
            for bucket in collisions
        ),
        "interpretation": (
            "These are polarity collisions after graph projection, not contradiction gold; "
            "context, state dimension, dose/time, mechanism, and curation must be adjudicated."
        ),
    }


def signor_entity(row: dict[str, str], side: str) -> tuple[str, str]:
    identifier = row[f"ID{side}"].strip()
    if identifier:
        return row[f"DATABASE{side}"].strip(), identifier
    return "NAME", row[f"ENTITY{side}"].strip().strip('"')


def audit_signor(path: Path) -> dict:
    all_rows: list[dict[str, str]] = []
    signed: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for source_row in csv.DictReader(handle, delimiter="\t"):
            all_rows.append(source_row)
            effect = source_row["EFFECT"].strip().strip('"')
            if effect.startswith("up-regulates"):
                sign = "+"
            elif effect.startswith("down-regulates"):
                sign = "-"
            else:
                continue
            signed.append(
                {
                    "source": signor_entity(source_row, "A"),
                    "target": signor_entity(source_row, "B"),
                    "sign": sign,
                    "taxon": source_row["TAX_ID"].strip(),
                    "cell": source_row["CELL_DATA"].strip(),
                    "tissue": source_row["TISSUE_DATA"].strip(),
                    "direct": source_row["DIRECT"].strip(),
                    "publication": source_row["PMID"].strip(),
                    "evidence": source_row["SENTENCE"].strip().strip('"'),
                    "entity_a_name": source_row["ENTITYA"].strip().strip('"'),
                    "entity_b_name": source_row["ENTITYB"].strip().strip('"'),
                }
            )

    strict = [
        row
        for row in signed
        if row["taxon"] == "9606"
        and row["direct"] == "t"
        and (row["cell"] or row["tissue"])
    ]
    evidence_sentences = {row["evidence"] for row in signed if row["evidence"]}
    pmids = {row["publication"] for row in signed if row["publication"]}
    surface_mentions = Counter()
    for row in signed:
        sentence = row["evidence"].casefold()
        mentions = sum(
            bool(name and name.casefold() in sentence)
            for name in (row["entity_a_name"], row["entity_b_name"])
        )
        surface_mentions[str(mentions)] += 1

    return {
        "graph_semantics": {
            "scc_layer": "ground entity-ID graph; not a predicate-dependency graph",
            "recommended_node_layer": "typed biological state atom with compatible taxon/cell/tissue/residue",
            "publisher_endorses_naive_signed_transitive_closure": False,
        },
        "counts": {
            "all_records": len(all_rows),
            "signed_causal_records": len(signed),
            "human_signed_records": sum(row["taxon"] == "9606" for row in signed),
            "human_direct_signed_records": sum(
                row["taxon"] == "9606" and row["direct"] == "t" for row in signed
            ),
        },
        "context_coverage": {
            "cell_nonempty": sum(bool(row["cell"]) for row in signed),
            "tissue_nonempty": sum(bool(row["tissue"]) for row in signed),
            "either_cell_or_tissue_nonempty": sum(
                bool(row["cell"] or row["tissue"]) for row in signed
            ),
        },
        "profiles": {
            "unstratified_signed_entity_graph": graph_profile(
                [(row["source"], row["target"]) for row in signed]
            ),
            "strict_human_direct_exact_nonempty_context": grouped_graph_profile(
                strict, lambda row: (row["taxon"], row["cell"], row["tissue"])
            ),
        },
        "evidence_quality": {
            "records_with_evidence_sentence": sum(bool(row["evidence"]) for row in signed),
            "unique_evidence_sentences": len(evidence_sentences),
            "records_with_pmid": sum(bool(row["publication"]) for row in signed),
            "unique_pmids": len(pmids),
            "surface_entity_mentions_per_record": dict(sorted(surface_mentions.items())),
            "provenance_note": (
                "Sentences are extracted from source articles and human-validated/curated; "
                "some candidates are first proposed by INDRA, so not all were manually transcribed from scratch."
            ),
        },
        "polarity_overlap": opposite_sign_audit(
            signed,
            context_fields=("taxon", "cell", "tissue"),
            detailed_fields=("cell", "tissue"),
        ),
        "benchmark_use": (
            "Main candidate only after typed-state and exact-context filtering; raw dual-sign pairs "
            "must be treated as context-resolution cases, not contradictions."
        ),
    }


XBEL_NS = "{http://belframework.org/schema/1.0/xbel}"


def xbel_attr(element: ET.Element, name: str) -> str:
    return element.attrib.get(XBEL_NS + name, "")


def xbel_term(term: ET.Element | None) -> str | None:
    if term is None:
        return None
    arguments: list[str] = []
    for child in term:
        if child.tag == XBEL_NS + "parameter":
            arguments.append(
                f"{xbel_attr(child, 'ns')}:{''.join(child.itertext()).strip()}"
            )
        elif child.tag == XBEL_NS + "term":
            nested = xbel_term(child)
            if nested is not None:
                arguments.append(nested)
    return f"{xbel_attr(term, 'function')}({','.join(arguments)})"


def xbel_endpoint(statement: ET.Element, side: str) -> str | None:
    wrapper = statement.find(XBEL_NS + side)
    return xbel_term(wrapper.find(XBEL_NS + "term")) if wrapper is not None else None


def xbel_annotations(statement: ET.Element) -> tuple[tuple[str, str], ...]:
    annotation_group = statement.find(XBEL_NS + "annotationGroup")
    if annotation_group is None:
        return ()
    return tuple(
        sorted(
            (
                xbel_attr(annotation, "refID"),
                "".join(annotation.itertext()).strip(),
            )
            for annotation in annotation_group.findall(XBEL_NS + "annotation")
        )
    )


def xbel_citation_and_evidence(statement: ET.Element) -> tuple[str, str, str]:
    annotation_group = statement.find(XBEL_NS + "annotationGroup")
    if annotation_group is None:
        return "", "", ""
    citation = annotation_group.find(XBEL_NS + "citation")
    evidence = annotation_group.find(XBEL_NS + "evidence")
    reference = citation.find(XBEL_NS + "reference") if citation is not None else None
    return (
        xbel_attr(citation, "type") if citation is not None else "",
        "".join(reference.itertext()).strip() if reference is not None else "",
        "".join(evidence.itertext()).strip() if evidence is not None else "",
    )


def audit_openbel(path: Path) -> dict:
    with gzip.open(path, "rb") as handle:
        root = ET.parse(handle).getroot()

    header = root.find(XBEL_NS + "header")
    header_version = ""
    header_license = ""
    if header is not None:
        version = header.find(XBEL_NS + "version")
        license_element = header.find(
            XBEL_NS + "licenseGroup/" + XBEL_NS + "license"
        )
        header_version = "".join(version.itertext()).strip() if version is not None else ""
        header_license = (
            "".join(license_element.itertext()).strip()
            if license_element is not None
            else ""
        )

    top_level_statements = [
        statement
        for group in root.findall(XBEL_NS + "statementGroup")
        for statement in group.findall(XBEL_NS + "statement")
    ]
    all_statement_objects = list(root.iter(XBEL_NS + "statement"))
    causal_relationships = {
        "increases": "+",
        "directlyIncreases": "+",
        "decreases": "-",
        "directlyDecreases": "-",
    }
    annotation_coverage = Counter()
    statements_with_evidence = 0
    statements_with_numeric_pmid = 0
    records: list[dict] = []
    for statement in top_level_statements:
        context = xbel_annotations(statement)
        annotation_coverage.update(key for key, _ in context)
        citation_type, citation_reference, evidence = xbel_citation_and_evidence(statement)
        statements_with_evidence += bool(evidence)
        statements_with_numeric_pmid += (
            citation_type == "PubMed" and citation_reference.isdigit()
        )
        relationship = xbel_attr(statement, "relationship")
        if relationship not in causal_relationships:
            continue
        source = xbel_endpoint(statement, "subject")
        target = xbel_endpoint(statement, "object")
        if source is None or target is None:
            continue
        records.append(
            {
                "source": source,
                "target": target,
                "sign": causal_relationships[relationship],
                "relationship": relationship,
                "context": context,
                "publication": citation_reference,
                "evidence": evidence,
                "numeric_pmid": citation_type == "PubMed" and citation_reference.isdigit(),
            }
        )

    strict = [
        row
        for row in records
        if row["numeric_pmid"]
        and row["evidence"]
        and any(key != "Species" and value for key, value in row["context"])
    ]
    strict_direct = [
        row for row in strict if row["relationship"].startswith("directly")
    ]
    collision_records = [
        {
            **row,
            "exact_context": row["context"],
            "detailed_context": tuple(
                item for item in row["context"] if item[0] != "Species"
            ),
        }
        for row in records
    ]

    return {
        "graph_semantics": {
            "scc_layer": "typed BEL term/state graph; not a predicate-dependency graph",
            "typed_state_examples": [
                "proteinAbundance",
                "kinaseActivity",
                "proteinModification",
                "biologicalProcess",
            ],
            "publisher_endorses_naive_signed_transitive_closure": False,
        },
        "header": {
            "version": header_version,
            "license": header_license,
        },
        "counts": {
            "top_level_statements": len(top_level_statements),
            "nested_statement_objects": len(all_statement_objects)
            - len(top_level_statements),
            "causal_typed_term_to_term_records": len(records),
            "top_level_statements_with_evidence": statements_with_evidence,
            "top_level_statements_with_numeric_pmid": statements_with_numeric_pmid,
            "causal_records_with_numeric_pmid_and_evidence": sum(
                row["numeric_pmid"] and bool(row["evidence"]) for row in records
            ),
        },
        "context_annotation_coverage": dict(sorted(annotation_coverage.items())),
        "profiles": {
            "unstratified_typed_state_graph": graph_profile(
                [(row["source"], row["target"]) for row in records]
            ),
            "exact_detailed_context_numeric_pmid_evidence": grouped_graph_profile(
                strict, lambda row: row["context"]
            ),
            "exact_detailed_context_numeric_pmid_evidence_direct_only": grouped_graph_profile(
                strict_direct, lambda row: row["context"]
            ),
        },
        "evidence_quality": {
            "evidence_type": "curator-selected source-article passage plus citation and context",
            "known_context_qc_flags_from_manual_spot_check": [
                "Some records combine HUVEC cell line with monocyte context.",
                "Some records label INS-1 cell with human species although INS-1 is rat-derived.",
                "Some direct SCCs encode activity<->phosphosite state coupling rather than dynamic feedback.",
            ],
            "context_consistency_requires_ontology_validation": True,
        },
        "polarity_overlap": opposite_sign_audit(
            collision_records,
            context_fields=("exact_context",),
            detailed_fields=("detailed_context",),
        ),
        "benchmark_use": (
            "Best external typed-state plus passage-grounded candidate after species/cell-line "
            "consistency checks and removal of definitional state-coupling cycles."
        ),
    }


AOP_NS = "{http://www.aopkb.org/aop-xml}"


def aop_path(path: str) -> str:
    return "/".join(AOP_NS + part for part in path.split("/"))


def aop_text(element: ET.Element, path: str) -> str:
    child = element.find(aop_path(path))
    return "".join(child.itertext()).strip() if child is not None else ""


def aop_cycle_summary(
    aops: Sequence[ET.Element],
    ker_directions: dict[str, tuple[str, str]],
    kers: dict[str, ET.Element],
    *,
    status: str | None,
) -> dict:
    cyclic_aops: set[str] = set()
    component_sizes: list[int] = []
    unique_internal_kers: set[str] = set()
    ratings = Counter()
    for aop in aops:
        if status is not None and aop_text(aop, "status/oecd-status") != status:
            continue
        relationships = aop.find(AOP_NS + "key-event-relationships")
        members = relationships.findall(AOP_NS + "relationship") if relationships is not None else []
        rating_by_id = {
            member.attrib["id"]: aop_text(member, "evidence") for member in members
        }
        graph = nx.DiGraph(
            ker_directions[ker_id]
            for ker_id in rating_by_id
            if ker_id in ker_directions
        )
        components = [
            component
            for component in nx.strongly_connected_components(graph)
            if len(component) > 1
        ]
        if components:
            cyclic_aops.add(aop.attrib["id"])
        for component in components:
            component_sizes.append(len(component))
            for ker_id, (source, target) in ker_directions.items():
                if ker_id in rating_by_id and source in component and target in component:
                    unique_internal_kers.add(ker_id)
                    ratings[rating_by_id[ker_id]] += 1

    fields = {
        "description": "description",
        "references": "references",
        "biological_plausibility": "weight-of-evidence/biological-plausibility",
        "empirical_support": "weight-of-evidence/emperical-support-linkage",
        "applicability": "applicability",
    }
    return {
        "cyclic_aops": len(cyclic_aops),
        "scc_memberships": len(component_sizes),
        "scc_size_distribution": dict(sorted(Counter(component_sizes).items())),
        "largest_scc": max(component_sizes, default=0),
        "unique_internal_kers": len(unique_internal_kers),
        "internal_ker_evidence_completeness": {
            name: sum(bool(aop_text(kers[ker_id], path)) for ker_id in unique_internal_kers)
            for name, path in fields.items()
        },
        "aop_membership_relationship_ratings": dict(sorted(ratings.items())),
    }


def audit_aop_wiki(path: Path) -> dict:
    with gzip.open(path, "rb") as handle:
        root = ET.parse(handle).getroot()
    aops = root.findall(AOP_NS + "aop")
    key_events = root.findall(AOP_NS + "key-event")
    ker_list = root.findall(AOP_NS + "key-event-relationship")
    kers = {ker.attrib["id"]: ker for ker in ker_list}
    ker_directions = {
        ker_id: (
            aop_text(ker, "title/upstream-id"),
            aop_text(ker, "title/downstream-id"),
        )
        for ker_id, ker in kers.items()
        if aop_text(ker, "title/upstream-id") and aop_text(ker, "title/downstream-id")
    }
    license_counts = Counter(aop_text(aop, "status/wiki-license") for aop in aops)
    status_counts = Counter(
        aop_text(aop, "status/oecd-status")
        for aop in aops
        if aop_text(aop, "status/oecd-status")
    )
    ker_fields = {
        "description": "description",
        "references": "references",
        "biological_plausibility": "weight-of-evidence/biological-plausibility",
        "empirical_support": "weight-of-evidence/emperical-support-linkage",
        "feedback_field": "quantitative-understanding/feedforward-feedback-loops",
    }
    return {
        "graph_semantics": {
            "scc_layer": "typed key-event graph within an AOP; not a predicate-dependency graph",
            "edge_polarity_field_present": False,
            "state_direction_is_often_encoded_in_key_event_names": True,
            "publisher_endorses_naive_transitive_closure_as_biological_truth": False,
        },
        "counts": {
            "aops": len(aops),
            "key_events": len(key_events),
            "key_event_relationships": len(ker_list),
            "aop_license_counts": dict(sorted(license_counts.items())),
            "oecd_status_counts": dict(sorted(status_counts.items())),
        },
        "profiles": {
            "global_key_event_union_warning_context_collapsed": graph_profile(
                list(ker_directions.values())
            ),
            "within_aop_all_statuses": aop_cycle_summary(
                aops, ker_directions, kers, status=None
            ),
            "within_aop_oecd_endorsed": aop_cycle_summary(
                aops, ker_directions, kers, status="WPHA/WNT Endorsed"
            ),
            "within_aop_under_development": aop_cycle_summary(
                aops, ker_directions, kers, status="Under Development"
            ),
        },
        "evidence_quality": {
            "all_ker_field_coverage": {
                name: sum(bool(aop_text(ker, field)) for ker in ker_list)
                for name, field in ker_fields.items()
            },
            "evidence_type": (
                "expert-authored synthesis with references, biological plausibility, empirical support, "
                "and uncertainty; not a verbatim source sentence per edge"
            ),
            "license_filter": (
                "Key-event and KER pages are BY-SA; exclude All rights reserved AOP page text."
            ),
        },
        "overlap": {
            "unit_of_reuse": "The same shared KER may appear in multiple AOPs.",
            "split_policy": "Split by entire AOP/KER component, never by random edge.",
        },
        "benchmark_use": (
            "Authoritative small feedback challenge: prefer OECD-endorsed within-AOP cycles; "
            "never use the global key-event union SCC as a coherent context."
        ),
    }


def audit_omnipath(path: Path) -> dict:
    counts = Counter()
    resources = Counter()
    pmids: set[str] = set()
    extra_attribute_keys = Counter()
    raw_signed_edges: list[tuple[str, str]] = []
    consensus_exclusive_edges: list[tuple[str, str]] = []
    no_signor_consensus_edges: list[tuple[str, str]] = []
    rows_with_signor_family = 0
    fieldnames: list[str] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fieldnames = reader.fieldnames or []
        for row in reader:
            counts["rows"] += 1
            positive = row["is_stimulation"] == "True"
            negative = row["is_inhibition"] == "True"
            consensus_positive = row["consensus_stimulation"] == "True"
            consensus_negative = row["consensus_inhibition"] == "True"
            counts["directed"] += row["is_directed"] == "True"
            counts["signed"] += positive or negative
            counts["raw_both_signs"] += positive and negative
            counts["consensus_signed"] += consensus_positive or consensus_negative
            counts["consensus_both_signs"] += consensus_positive and consensus_negative
            counts["rows_with_references"] += bool(row["references"])
            counts["rows_with_evidences_json"] += bool(row["evidences"])
            source_set = {source for source in row["sources"].split(";") if source}
            resources.update(source_set)
            for reference in row["references"].split(";"):
                candidate = reference.rsplit(":", 1)[-1]
                if candidate.isdigit():
                    pmids.add(candidate)
            try:
                extra_attributes = json.loads(row["extra_attrs"])
            except json.JSONDecodeError:
                extra_attributes = {}
            extra_attribute_keys.update(extra_attributes.keys())
            edge = (row["source_genesymbol"], row["target_genesymbol"])
            if positive or negative:
                raw_signed_edges.append(edge)
            if consensus_positive ^ consensus_negative:
                consensus_exclusive_edges.append(edge)
            has_signor = bool(source_set & {"SIGNOR", "SIGNOR_ProtMapper"})
            rows_with_signor_family += has_signor
            if not has_signor and consensus_positive ^ consensus_negative:
                no_signor_consensus_edges.append(edge)

    edge_context_names = {
        "cell",
        "cell_type",
        "cell_line",
        "tissue",
        "anatomy",
        "dose",
        "time",
        "condition",
    }
    return {
        "graph_semantics": {
            "scc_layer": "human entity/gene-symbol graph integrated across resources; not a predicate-dependency graph",
            "publisher_endorses_naive_signed_transitive_closure": False,
        },
        "counts": {
            "rows": counts["rows"],
            "directed_rows": counts["directed"],
            "signed_rows": counts["signed"],
            "consensus_signed_rows": counts["consensus_signed"],
            "unique_pmids": len(pmids),
            "distinct_resources": len(resources),
        },
        "profiles": {
            "raw_signed_entity_graph": graph_profile(raw_signed_edges),
            "consensus_exclusive_sign_entity_graph": graph_profile(
                consensus_exclusive_edges
            ),
            "no_signor_family_consensus_exclusive_graph": graph_profile(
                no_signor_consensus_edges
            ),
        },
        "evidence_quality": {
            "rows_with_references": counts["rows_with_references"],
            "rows_with_evidences_json": counts["rows_with_evidences_json"],
            "source_passage_column_present": bool(
                {"sentence", "evidence_sentence", "supporting_text"} & set(fieldnames)
            ),
            "universal_edge_context_columns_present": sorted(
                edge_context_names & set(fieldnames)
            ),
            "extra_attribute_key_count": len(extra_attribute_keys),
            "extra_attribute_keys": sorted(extra_attribute_keys),
            "interpretation": (
                "The evidences JSON carries resource/PMID provenance and resource-specific attributes, "
                "but the table has neither source passages nor systematic edge-level cell/tissue/time/dose context."
            ),
        },
        "polarity_overlap": {
            "rows_with_both_raw_signs": counts["raw_both_signs"],
            "rows_with_both_consensus_signs": counts["consensus_both_signs"],
            "interpretation": "Integrated evidence disagreement/context mixture, not contradiction gold.",
        },
        "source_overlap": {
            "rows_with_signor_or_signor_protmapper": rows_with_signor_family,
            "fraction_rows_with_signor_family": round(
                rows_with_signor_family / counts["rows"], 6
            ),
            "rows_without_signor_family": counts["rows"] - rows_with_signor_family,
            "top_resources_by_row_count": [
                {"resource": resource, "rows": count}
                for resource, count in resources.most_common(15)
            ],
        },
        "license_note": (
            "OmniPath has no single data license; license=academic filters upstream resources "
            "but does not create a new aggregate redistribution license."
        ),
        "benchmark_use": (
            "Scale/transfer stress test only. Remove SIGNOR-family evidence for external evaluation; "
            "do not treat the giant context-free SCC or dual signs as gold."
        ),
    }


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=script_dir / "raw" / "biology",
        help="Directory containing ignored raw snapshots.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "biology_feedback_audit.json",
        help="Compact tracked JSON output.",
    )
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="Download missing raw snapshots from the recorded URLs.",
    )
    parser.add_argument(
        "--allow-hash-mismatch",
        action="store_true",
        help="Audit a newer/different snapshot while recording the mismatch.",
    )
    args = parser.parse_args()

    paths, source_metadata = prepare_files(
        args.raw_root,
        download_missing=args.download_missing,
        allow_hash_mismatch=args.allow_hash_mismatch,
    )
    result = {
        "schema_version": 1,
        "audit_as_of": AUDIT_DATE,
        "generated_by": Path(__file__).name,
        "semantic_guardrails": {
            "scc_definition": (
                "All SCCs are computed over ground entities or typed states; none is a "
                "predicate-dependency SCC."
            ),
            "closure_gold": (
                "Any recursive closure label must be generated by a declared reference engine "
                "under benchmark rules; publishers do not certify naive transitive closure as biology."
            ),
            "polarity_collision": (
                "Opposite signs after graph projection are context-resolution candidates, "
                "not logical contradictions without state/context/dose/time adjudication."
            ),
        },
        "datasets": {
            "signor": {
                "source": source_metadata["signor"],
                "audit": audit_signor(paths["signor"]),
            },
            "openbel_large_corpus": {
                "source": source_metadata["openbel"],
                "audit": audit_openbel(paths["openbel"]),
            },
            "aop_wiki": {
                "source": source_metadata["aop_wiki"],
                "audit": audit_aop_wiki(paths["aop_wiki"]),
            },
            "omnipath": {
                "source": source_metadata["omnipath"],
                "audit": audit_omnipath(paths["omnipath"]),
            },
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
