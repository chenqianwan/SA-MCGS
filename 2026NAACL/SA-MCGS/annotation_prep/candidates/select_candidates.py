#!/usr/bin/env python3
"""Freeze an outcome-blind 36-post expert-audit sample.

The selector intentionally never reads method metrics.  It uses only the locked
80-case identity plan, the identifiers of the 12 legacy expert cases, and the
following pre-declared constraints:

* legal domains only (SEC EX-21, BGB, CUAD);
* retain all 12 legacy expert cases;
* exactly 12 post cases per domain;
* exactly 3 cases in every domain x injection-template cell (9/template);
* maximize distinct source physical SCCs;
* among maximum-breadth solutions, minimize global size-bin imbalance;
* deterministic SHA-256 ranks break any remaining ties.

The source physical fingerprint excludes injection metadata and injected text.
It is derived from domain, dataset revision, source clause IDs, and typed
internal edges.  The script also reloads the original graphs and exports the
unmodified pre sources for an independently checkable pre/post mapping.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT))
CASE_PLAN_PATH = (
    REPO_ROOT
    / "2026NAACL/SA-MCGS/validation/identity_stage2_80/case_plan.json"
)
LEGACY_CASES_PATH = (
    REPO_ROOT
    / "experiments/main_experiment/paper_assets/human_annotation_pack/"
    "human_annotation_cases.csv"
)

DOMAINS = ("sec_ex21", "bgb", "cuad")
TEMPLATES = (
    "direct_mutex",
    "condition_trigger",
    "handoff_invariant",
    "temporal_gate",
)
SIZE_BINS = ("small_9_11", "medium_12_19", "large_20_plus")
CELL_TARGET = 3
TIE_SEED = "arr-oct-2026-expert-audit-v1"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def canonical_weight(value: Any) -> str:
    return format(float(value), ".17g")


def canonical_edges(edges: Iterable[Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for edge in edges:
        if isinstance(edge, dict):
            source = str(edge["source"])
            target = str(edge["target"])
            kind = enum_value(edge.get("dependency_type", "references"))
            weight = canonical_weight(edge.get("weight", 1.0))
        else:
            source = str(edge.source)
            target = str(edge.target)
            kind = enum_value(edge.dependency_type)
            weight = canonical_weight(edge.weight)
        out.append(
            {
                "source": source,
                "target": target,
                "dependency_type": kind,
                "weight": weight,
            }
        )
    return sorted(
        out,
        key=lambda edge: (
            edge["source"],
            edge["target"],
            edge["dependency_type"],
            edge["weight"],
        ),
    )


def source_identity_payload(row: dict[str, Any]) -> dict[str, Any]:
    identity = row["planned_case_identity"]
    return {
        "version": "source_physical_scc_identity_v1",
        "domain": row["domain"],
        "dataset_revision": identity["dataset_revision"],
        "ordered_clause_ids": sorted(identity["ordered_clause_ids"]),
        "typed_internal_edges": canonical_edges(identity["typed_internal_edges"]),
    }


def size_bin(size: int) -> str:
    if size <= 11:
        return SIZE_BINS[0]
    if size <= 19:
        return SIZE_BINS[1]
    return SIZE_BINS[2]


def tie_rank(case_uid: str) -> int:
    digest = hashlib.sha256(f"{TIE_SEED}|{case_uid}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def load_case_plan() -> list[dict[str, Any]]:
    rows = json.loads(CASE_PLAN_PATH.read_text(encoding="utf-8"))
    if len(rows) != 80:
        raise AssertionError(f"expected locked 80-case plan, found {len(rows)}")
    for row in rows:
        row["source_identity_payload"] = source_identity_payload(row)
        row["source_physical_fingerprint"] = sha256_json(
            row["source_identity_payload"]
        )
        row["size_bin"] = size_bin(int(row["scc_size"]))
        row["tie_rank"] = tie_rank(row["case_uid"])
    return rows


def load_legacy_cases() -> list[dict[str, str]]:
    with LEGACY_CASES_PATH.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 12:
        raise AssertionError(f"expected 12 legacy expert cases, found {len(rows)}")
    return rows


def match_legacy_cases(
    legal_pool: list[dict[str, Any]],
    legacy_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    selected: list[dict[str, Any]] = []
    legacy_by_case_uid: dict[str, dict[str, str]] = {}
    for legacy in legacy_rows:
        matches = []
        for row in legal_pool:
            injection = row["planned_injection_identity"]
            if (
                row["domain"] == legacy["domain"]
                and row["template"] == legacy["template"]
                and int(row["scc_size"]) == int(legacy["scc_size"])
                and injection.get("root_node") == legacy["root_node"]
                and injection.get("witness_node") == legacy["witness_node"]
                and (injection.get("bridge_node") or "") == (legacy["bridge_node"] or "")
            ):
                matches.append(row)
        if len(matches) != 1:
            raise AssertionError(
                f"legacy case {legacy['case_id']} matched {len(matches)} locked cases"
            )
        row = matches[0]
        if row["case_uid"] in legacy_by_case_uid:
            raise AssertionError(f"duplicate legacy match: {row['case_uid']}")
        selected.append(row)
        legacy_by_case_uid[row["case_uid"]] = legacy
    return selected, legacy_by_case_uid


@dataclass(frozen=True)
class Option:
    rows: tuple[dict[str, Any], ...]
    source_fps: frozenset[str]
    size_counts: tuple[int, int, int]
    tie_total: int


@dataclass
class DomainState:
    rows: tuple[dict[str, Any], ...]
    size_counts: tuple[int, int, int]
    source_counts: Counter[str]
    tie_total: int


def vector_add(*vectors: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sum(parts) for parts in zip(*vectors))


def make_option(rows: tuple[dict[str, Any], ...]) -> Option:
    bins = Counter(row["size_bin"] for row in rows)
    return Option(
        rows=rows,
        source_fps=frozenset(row["source_physical_fingerprint"] for row in rows),
        size_counts=tuple(bins[name] for name in SIZE_BINS),
        tie_total=sum(int(row["tie_rank"]) for row in rows),
    )


def enumerate_best_domain_states(
    domain: str,
    pool: list[dict[str, Any]],
    legacy: list[dict[str, Any]],
) -> tuple[int, dict[tuple[int, int, int], DomainState]]:
    legacy_domain = [row for row in legacy if row["domain"] == domain]
    legacy_uids = {row["case_uid"] for row in legacy_domain}
    legacy_bins = Counter(row["size_bin"] for row in legacy_domain)
    legacy_bin_vector = tuple(legacy_bins[name] for name in SIZE_BINS)
    legacy_source_counts = Counter(
        row["source_physical_fingerprint"] for row in legacy_domain
    )
    legacy_tie = sum(int(row["tie_rank"]) for row in legacy_domain)

    options_by_template: list[list[Option]] = []
    for template in TEMPLATES:
        old_count = sum(row["template"] == template for row in legacy_domain)
        need = CELL_TARGET - old_count
        if need < 0:
            raise AssertionError(f"legacy {domain}/{template} exceeds cell target")
        candidates = sorted(
            (
                row
                for row in pool
                if row["domain"] == domain
                and row["template"] == template
                and row["case_uid"] not in legacy_uids
            ),
            key=lambda row: row["case_uid"],
        )
        options_by_template.append(
            [make_option(combo) for combo in itertools.combinations(candidates, need)]
        )

    maximum_breadth = -1
    best_by_size: dict[tuple[int, int, int], DomainState] = {}
    for choices in itertools.product(*options_by_template):
        rows = tuple(row for option in choices for row in option.rows)
        source_counts = legacy_source_counts.copy()
        for row in rows:
            source_counts[row["source_physical_fingerprint"]] += 1
        breadth = len(source_counts)
        if breadth < maximum_breadth:
            continue
        if breadth > maximum_breadth:
            maximum_breadth = breadth
            best_by_size.clear()

        final_bins = vector_add(
            legacy_bin_vector,
            *(option.size_counts for option in choices),
        )
        tie_total = legacy_tie + sum(option.tie_total for option in choices)
        state = DomainState(
            rows=tuple(legacy_domain) + rows,
            size_counts=final_bins,
            source_counts=source_counts,
            tie_total=tie_total,
        )
        concentration = (
            max(source_counts.values()),
            sum(count * count for count in source_counts.values()),
            tie_total,
        )
        incumbent = best_by_size.get(final_bins)
        if incumbent is None:
            best_by_size[final_bins] = state
        else:
            incumbent_concentration = (
                max(incumbent.source_counts.values()),
                sum(count * count for count in incumbent.source_counts.values()),
                incumbent.tie_total,
            )
            if concentration < incumbent_concentration:
                best_by_size[final_bins] = state

    return maximum_breadth, best_by_size


def choose_global_sample(
    pool: list[dict[str, Any]],
    legacy: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    domain_states: dict[str, dict[tuple[int, int, int], DomainState]] = {}
    domain_breadth: dict[str, int] = {}
    for domain in DOMAINS:
        breadth, states = enumerate_best_domain_states(domain, pool, legacy)
        domain_breadth[domain] = breadth
        domain_states[domain] = states

    target_per_bin = 36 // len(SIZE_BINS)
    best_score: tuple[Any, ...] | None = None
    best_rows: list[dict[str, Any]] | None = None
    for states in itertools.product(*(domain_states[domain].values() for domain in DOMAINS)):
        bins = vector_add(*(state.size_counts for state in states))
        source_counts = Counter()
        for state in states:
            source_counts.update(state.source_counts)
        tie_total = sum(state.tie_total for state in states)
        score = (
            sum((count - target_per_bin) ** 2 for count in bins),
            max(bins) - min(bins),
            max(source_counts.values()),
            sum(count * count for count in source_counts.values()),
            tie_total,
        )
        if best_score is None or score < best_score:
            best_score = score
            best_rows = [row for state in states for row in state.rows]

    assert best_rows is not None
    return best_rows, domain_breadth


def load_original_graphs() -> dict[str, Any]:
    # Import lazily so manifest-only validation remains quick to inspect.
    from experiments.cross_domain.run_cross_domain_battle import (
        load_bgb_graph,
        load_cuad_graph,
        load_sec_graph,
    )

    return {
        "sec_ex21": load_sec_graph(),
        "bgb": load_bgb_graph(),
        "cuad": load_cuad_graph(),
    }


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def graph_internal_edges(graph: Any, clause_ids: set[str]) -> list[dict[str, str]]:
    return canonical_edges(
        edge
        for edge in graph.edges
        if edge.source in clause_ids and edge.target in clause_ids
    )


def build_pre_sources(
    selected: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    graphs = load_original_graphs()
    representative: dict[str, dict[str, Any]] = {}
    for row in selected:
        representative.setdefault(row["source_physical_fingerprint"], row)

    pre_sources: list[dict[str, Any]] = []
    for source_fp, row in sorted(
        representative.items(),
        key=lambda item: (
            DOMAINS.index(item[1]["domain"]),
            -int(item[1]["scc_size"]),
            item[0],
        ),
    ):
        domain = row["domain"]
        graph = graphs[domain]
        clause_ids = sorted(row["source_identity_payload"]["ordered_clause_ids"])
        missing = [clause_id for clause_id in clause_ids if clause_id not in graph.clauses]
        if missing:
            raise AssertionError(f"{domain} source {source_fp} missing clauses: {missing}")

        actual_edges = graph_internal_edges(graph, set(clause_ids))
        planned_edges = row["source_identity_payload"]["typed_internal_edges"]
        if actual_edges != planned_edges:
            raise AssertionError(
                f"{domain} source {source_fp} original internal edges differ from plan"
            )

        clauses = []
        text_hashes = []
        for clause_id in clause_ids:
            clause = graph.clauses[clause_id]
            content = str(clause.content or "")
            clauses.append(
                {
                    "id": clause_id,
                    "title": str(clause.title or ""),
                    "content": content,
                    "clause_type": enum_value(clause.clause_type),
                }
            )
            text_hashes.append(
                {
                    "id": clause_id,
                    "normalized_text_sha256": "sha256:"
                    + hashlib.sha256(normalize_text(content).encode("utf-8")).hexdigest(),
                }
            )

        content_payload = {
            "version": "unmodified_pre_source_content_v1",
            "source_physical_fingerprint": source_fp,
            "domain": domain,
            "dataset_revision": row["source_identity_payload"]["dataset_revision"],
            "ordered_clause_ids": clause_ids,
            "normalized_clause_text_hashes": text_hashes,
            "typed_internal_edges": actual_edges,
        }
        short_fp = source_fp.removeprefix("sha256:")[:12]
        pre_sources.append(
            {
                "pre_source_id": f"pre_{domain}_{int(row['scc_size']):02d}_{short_fp}",
                "source_physical_fingerprint": source_fp,
                "pre_content_fingerprint": sha256_json(content_payload),
                "domain": domain,
                "source_scc_size": len(clause_ids),
                "dataset_revision": row["source_identity_payload"]["dataset_revision"],
                "unmodified": True,
                "annotation_action": "new_annotation",
                "ordered_clause_ids": clause_ids,
                "typed_internal_edges": actual_edges,
                "clauses": clauses,
            }
        )
    return pre_sources, graphs


def build_post_materials(
    selected: list[dict[str, Any]],
    legacy_map: dict[str, dict[str, str]],
    graphs: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    from experiments.cross_domain.inject_defect import inject_defect
    from src.models.graph import SCCInfo

    materials: list[dict[str, Any]] = []
    legacy_text_matches = 0
    for row in selected:
        domain = row["domain"]
        graph = graphs[domain]
        clause_ids = list(row["planned_scc_clause_ids"])
        clause_set = set(clause_ids)
        internal_edges = [
            edge
            for edge in graph.edges
            if edge.source in clause_set and edge.target in clause_set
        ]
        source_scc = SCCInfo(
            id=f"source_{row['source_physical_fingerprint'][-12:]}",
            clause_ids=clause_ids,
            internal_edges=internal_edges,
            size=len(clause_ids),
        )
        injection = row["planned_injection_identity"]
        post_graph, injected_root = inject_defect(
            graph,
            source_scc,
            domain,
            seed=int(injection.get("seed", 42)),
            profile=str(injection["profile"]),
            conflict_template=row["template"],
            conflict_severity=str(injection["conflict_severity"]),
        )
        rebuilt = post_graph.clauses[injected_root].metadata
        rebuilt_identity = {
            "root_node": injected_root,
            "witness_node": rebuilt.get("_inject_witness_node"),
            "bridge_node": rebuilt.get("_inject_bridge_node"),
            "risk_nodes": rebuilt.get("_inject_risk_nodes") or [],
            "affected_nodes": rebuilt.get("_inject_affected_nodes") or [],
        }
        expected_identity = {
            "root_node": injection.get("root_node"),
            "witness_node": injection.get("witness_node"),
            "bridge_node": injection.get("bridge_node"),
            "risk_nodes": injection.get("risk_nodes") or [],
            "affected_nodes": injection.get("affected_nodes") or [],
        }
        if rebuilt_identity != expected_identity:
            raise AssertionError(
                f"rebuilt post identity differs for {row['case_id']}: "
                f"{rebuilt_identity} != {expected_identity}"
            )

        nodes = []
        for clause_id in clause_ids:
            clause = post_graph.clauses[clause_id]
            title = normalize_text(str(clause.title or clause_id))
            raw_content = str(clause.content or clause.title or clause_id).strip()
            legacy_display_text = (
                f"{title}\n\n{raw_content}"
                if title
                and raw_content
                and not normalize_text(raw_content).startswith(title)
                else raw_content or title
            )
            nodes.append(
                {
                    "id": clause_id,
                    "title": title,
                    "content": raw_content,
                    "text": raw_content,
                    "legacy_display_text": legacy_display_text,
                    "clause_type": enum_value(clause.clause_type),
                }
            )
        content_payload = {
            "version": "post_injected_text_content_v1",
            "post_case_uid": row["case_uid"],
            "nodes": [
                {
                    "id": node["id"],
                    "normalized_text": normalize_text(node["content"]),
                }
                for node in nodes
            ],
        }
        legacy = legacy_map.get(row["case_uid"])
        legacy_match: bool | None = None
        if legacy:
            legacy_path = (
                LEGACY_CASES_PATH.parent
                / "materials"
                / f"{legacy['case_id']}.json"
            )
            legacy_material = json.loads(legacy_path.read_text(encoding="utf-8"))
            legacy_text = {
                node["node_id"]: normalize_text(node["text_en"])
                for node in legacy_material["full_nodes"]
            }
            rebuilt_text = {
                node["id"]: normalize_text(node["legacy_display_text"])
                for node in nodes
            }
            legacy_match = legacy_text == rebuilt_text
            if not legacy_match:
                differing = sorted(
                    key
                    for key in set(legacy_text) | set(rebuilt_text)
                    if legacy_text.get(key) != rebuilt_text.get(key)
                )
                raise AssertionError(
                    f"legacy material text differs for {legacy['case_id']}: {differing}"
                )
            legacy_text_matches += 1

        materials.append(
            {
                "post_case_uid": row["case_uid"],
                "canonical_case_id": row["case_id"],
                "source_physical_fingerprint": row["source_physical_fingerprint"],
                "domain": domain,
                "template": row["template"],
                "annotation_action": (
                    "reuse_legacy_label" if legacy else "new_annotation"
                ),
                "legacy_case_id": legacy["case_id"] if legacy else None,
                "legacy_material_text_match": legacy_match,
                "post_content_fingerprint": sha256_json(content_payload),
                "nodes": nodes,
            }
        )
    return materials, legacy_text_matches


def validate_selection(
    legal_pool: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    legacy_map: dict[str, dict[str, str]],
    pre_sources: list[dict[str, Any]],
    legacy_material_text_matches: int,
) -> dict[str, Any]:
    selected_uids = [row["case_uid"] for row in selected]
    if len(selected) != 36 or len(set(selected_uids)) != 36:
        raise AssertionError("selection must contain 36 unique post cases")
    if not set(legacy_map).issubset(selected_uids):
        raise AssertionError("not all 12 legacy expert cases were retained")
    domain_counts = Counter(row["domain"] for row in selected)
    template_counts = Counter(row["template"] for row in selected)
    cell_counts = Counter((row["domain"], row["template"]) for row in selected)
    size_counts = Counter(row["size_bin"] for row in selected)
    source_counts = Counter(row["source_physical_fingerprint"] for row in selected)
    pool_source_fps = {row["source_physical_fingerprint"] for row in legal_pool}

    if domain_counts != Counter({domain: 12 for domain in DOMAINS}):
        raise AssertionError(f"domain imbalance: {domain_counts}")
    if template_counts != Counter({template: 9 for template in TEMPLATES}):
        raise AssertionError(f"template imbalance: {template_counts}")
    if any(cell_counts[(domain, template)] != 3 for domain in DOMAINS for template in TEMPLATES):
        raise AssertionError(f"domain-template cell imbalance: {cell_counts}")
    if len(source_counts) != len(pool_source_fps):
        raise AssertionError(
            f"source breadth is not maximal: selected {len(source_counts)}, pool {len(pool_source_fps)}"
        )
    if len(pre_sources) != len(source_counts):
        raise AssertionError("pre-source export is not one-to-one with selected source SCCs")

    old_source_count = len(
        {
            row["source_physical_fingerprint"]
            for row in selected
            if row["case_uid"] in legacy_map
        }
    )
    if old_source_count != 7:
        raise AssertionError(f"legacy 12 should map to 7 physical SCCs, got {old_source_count}")
    if legacy_material_text_matches != 12:
        raise AssertionError(
            "all 12 rebuilt post texts must exactly match the frozen legacy materials"
        )

    return {
        "selection_version": "arr_oct_2026_expert_audit_36post_v1",
        "locked_pool_cases": 80,
        "locked_legal_pool_cases": len(legal_pool),
        "locked_legal_source_physical_sccs": len(pool_source_fps),
        "selected_post_cases": len(selected),
        "legacy_post_cases_reused": len(legacy_map),
        "new_post_cases": len(selected) - len(legacy_map),
        "selected_source_physical_sccs_U": len(source_counts),
        "legacy_source_physical_sccs": old_source_count,
        "legacy_post_texts_exactly_matched": legacy_material_text_matches,
        "domain_counts": dict(sorted(domain_counts.items())),
        "template_counts": dict(sorted(template_counts.items())),
        "domain_template_counts": {
            f"{domain}|{template}": cell_counts[(domain, template)]
            for domain in DOMAINS
            for template in TEMPLATES
        },
        "size_bin_definition": {
            SIZE_BINS[0]: "9-11 nodes",
            SIZE_BINS[1]: "12-19 nodes",
            SIZE_BINS[2]: "20+ nodes",
        },
        "size_bin_counts": {name: size_counts[name] for name in SIZE_BINS},
        "post_variants_per_source_distribution": dict(
            sorted(Counter(source_counts.values()).items())
        ),
        "source_breadth_proof": (
            "The locked legal pool contains 18 structural source fingerprints; "
            "the selected 36 contain all 18, so U=18 is the maximum possible breadth."
        ),
        "outcome_blind": True,
        "metric_fields_read_by_selector": [],
        "tie_seed": TIE_SEED,
    }


def write_outputs(
    selected: list[dict[str, Any]],
    legacy_map: dict[str, dict[str, str]],
    pre_sources: list[dict[str, Any]],
    post_materials: list[dict[str, Any]],
    validation: dict[str, Any],
) -> None:
    pre_by_fp = {row["source_physical_fingerprint"]: row for row in pre_sources}
    selected_sorted = sorted(
        selected,
        key=lambda row: (
            DOMAINS.index(row["domain"]),
            TEMPLATES.index(row["template"]),
            -int(row["scc_size"]),
            row["case_uid"],
        ),
    )

    post_rows: list[dict[str, Any]] = []
    for index, row in enumerate(selected_sorted, start=1):
        legacy = legacy_map.get(row["case_uid"])
        injection = row["planned_injection_identity"]
        pre = pre_by_fp[row["source_physical_fingerprint"]]
        post_rows.append(
            {
                "audit_post_id": f"post_{index:03d}",
                "canonical_case_id": row["case_id"],
                "post_case_uid": row["case_uid"],
                "legacy_label_reused": legacy is not None,
                "annotation_action": (
                    "reuse_legacy_label" if legacy else "new_annotation"
                ),
                "legacy_case_id": legacy["case_id"] if legacy else None,
                "legacy_model": legacy["model"] if legacy else None,
                "domain": row["domain"],
                "source_scc_size": int(row["scc_size"]),
                "size_bin": row["size_bin"],
                "template": row["template"],
                "severity": injection.get("conflict_severity"),
                "source_physical_fingerprint": row["source_physical_fingerprint"],
                "pre_source_id": pre["pre_source_id"],
                "pre_content_fingerprint": pre["pre_content_fingerprint"],
                "root_node": injection.get("root_node"),
                "witness_node": injection.get("witness_node"),
                "bridge_node": injection.get("bridge_node"),
                "risk_nodes": injection.get("risk_nodes") or [],
                "affected_nodes": injection.get("affected_nodes") or [],
                "source_result_repo_relpath": row["source_result_repo_relpath"],
                "source_record_locator": {
                    "method": "sa-mcgs",
                    "model": row["model"],
                    "domain": row["domain"],
                    "scc_size": int(row["scc_size"]),
                    "source_scc_id": row["source_scc_id"],
                },
                "source_result_sha256": row["source_result_sha256"],
                "source_sa_record_sha256": row["source_sa_record_sha256"],
                "dataset_revision": row["source_identity_payload"]["dataset_revision"],
                "ordered_clause_ids": row["source_identity_payload"]["ordered_clause_ids"],
                "injection_identity": injection,
            }
        )

    (SCRIPT_DIR / "selected_post_36.json").write_text(
        json.dumps(post_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    csv_fields = [
        "audit_post_id",
        "canonical_case_id",
        "post_case_uid",
        "legacy_label_reused",
        "annotation_action",
        "legacy_case_id",
        "legacy_model",
        "domain",
        "source_scc_size",
        "size_bin",
        "template",
        "severity",
        "source_physical_fingerprint",
        "pre_source_id",
        "pre_content_fingerprint",
        "root_node",
        "witness_node",
        "bridge_node",
        "source_result_repo_relpath",
    ]
    with (SCRIPT_DIR / "selected_post_36.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(post_rows)

    (SCRIPT_DIR / "pre_sources_18.json").write_text(
        json.dumps(pre_sources, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (SCRIPT_DIR / "post_materials_36_internal.json").write_text(
        json.dumps(post_materials, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pre_csv_fields = [
        "pre_source_id",
        "source_physical_fingerprint",
        "pre_content_fingerprint",
        "domain",
        "source_scc_size",
        "dataset_revision",
        "unmodified",
        "annotation_action",
        "post_variant_count",
        "legacy_post_variant_count",
    ]
    post_counts = Counter(row["source_physical_fingerprint"] for row in post_rows)
    legacy_counts = Counter(
        row["source_physical_fingerprint"]
        for row in post_rows
        if row["legacy_label_reused"]
    )
    pre_summary_rows = []
    for row in pre_sources:
        summary = {key: row.get(key) for key in pre_csv_fields}
        summary["post_variant_count"] = post_counts[row["source_physical_fingerprint"]]
        summary["legacy_post_variant_count"] = legacy_counts[
            row["source_physical_fingerprint"]
        ]
        pre_summary_rows.append(summary)
    with (SCRIPT_DIR / "pre_sources_18.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=pre_csv_fields)
        writer.writeheader()
        writer.writerows(pre_summary_rows)

    validation["selected_post_manifest_sha256"] = "sha256:" + hashlib.sha256(
        (SCRIPT_DIR / "selected_post_36.json").read_bytes()
    ).hexdigest()
    validation["pre_source_manifest_sha256"] = "sha256:" + hashlib.sha256(
        (SCRIPT_DIR / "pre_sources_18.json").read_bytes()
    ).hexdigest()
    validation["post_materials_sha256"] = "sha256:" + hashlib.sha256(
        (SCRIPT_DIR / "post_materials_36_internal.json").read_bytes()
    ).hexdigest()

    post_by_uid = {row["post_case_uid"]: row for row in post_rows}
    source_groups = []
    for pre in pre_sources:
        fp = pre["source_physical_fingerprint"]
        grouped_posts = [
            row for row in post_rows if row["source_physical_fingerprint"] == fp
        ]
        source_groups.append(
            {
                "source_physical_fingerprint": fp,
                "pre_source_id": pre["pre_source_id"],
                "pre_annotation_action": "new_annotation",
                "pre_material_ref": (
                    f"pre_sources_18.json#pre_source_id={pre['pre_source_id']}"
                ),
                "post_case_uids": [row["post_case_uid"] for row in grouped_posts],
                "post_audit_ids": [row["audit_post_id"] for row in grouped_posts],
            }
        )
    master_manifest = {
        "manifest_version": "arr_oct_2026_expert_annotation_master_v1",
        "selection_validation_ref": "selection_validation.json",
        "counts": {
            "pre_presentations": len(pre_sources),
            "post_presentations": len(post_rows),
            "new_pre_presentations": len(pre_sources),
            "new_post_presentations": sum(
                row["annotation_action"] == "new_annotation" for row in post_rows
            ),
            "reused_post_presentations": sum(
                row["annotation_action"] == "reuse_legacy_label" for row in post_rows
            ),
            "frontend_new_annotation_presentations": len(pre_sources)
            + sum(row["annotation_action"] == "new_annotation" for row in post_rows),
        },
        "internal_only": True,
        "frontend_filter": {"annotation_action": "new_annotation"},
        "pre_material_file": "pre_sources_18.json",
        "post_material_file": "post_materials_36_internal.json",
        "pre_presentations": [
            {
                "presentation_id": pre["pre_source_id"],
                "phase": "pre",
                "annotation_action": "new_annotation",
                "source_physical_fingerprint": pre["source_physical_fingerprint"],
                "pre_content_fingerprint": pre["pre_content_fingerprint"],
                "material_ref": (
                    f"pre_sources_18.json#pre_source_id={pre['pre_source_id']}"
                ),
            }
            for pre in pre_sources
        ],
        "post_presentations": post_rows,
        "source_groups": source_groups,
    }
    (SCRIPT_DIR / "master_manifest.json").write_text(
        json.dumps(master_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    validation["master_manifest_sha256"] = "sha256:" + hashlib.sha256(
        (SCRIPT_DIR / "master_manifest.json").read_bytes()
    ).hexdigest()
    (SCRIPT_DIR / "selection_validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = f"""# 36-Post 候选集冻结说明

## 结果

- 从 locked 80-case 主实验中只取法律领域的 72 个 post variants；不读取任何方法得分或输赢字段。
- 最终冻结 36 个 post cases：SEC EX-21、BGB、CUAD 各 12 个；四种 template 各 9 个；每个 domain × template 单元格均为 3 个。
- 保留旧 expert audit 的全部 12 个 post cases；其余 24 个由预先声明的结构约束和固定 SHA-256 tie seed 选出。
- 36 个 post 映射到 **U={validation['selected_source_physical_sccs_U']}** 个 unmodified pre source SCC；覆盖 locked 法律池的全部 18 个 source physical SCC，因此 source breadth 已达可实现上限。
- Size bins（9–11 / 12–19 / 20+ nodes）为 **{validation['size_bin_counts'][SIZE_BINS[0]]} / {validation['size_bin_counts'][SIZE_BINS[1]]} / {validation['size_bin_counts'][SIZE_BINS[2]]}**。在“保留旧 12 + 全覆盖 18 sources + domain/template 精确平衡”约束下，本选择最小化了相对 12/12/12 的平方偏差。

## 身份口径

`source_physical_fingerprint` 只哈希 `domain + dataset_revision + sorted source clause IDs + typed internal edges`，明确排除 injection metadata、Tarjan `scc_id` 和注入后文本。它将 72 个法律 post variants 正确折叠为 18 个 source SCC，并将旧 12 个 cases 折叠为 7 个 source SCC。

`pre_sources_18.json` 是从原始 SEC/BGB/CUAD graph loader 重新读取的未注入文本和内部边。生成时逐个验证其 clause set 和 internal-edge signature 与 locked plan 一致；`pre_content_fingerprint` 再对实际原文内容进行固定。

## 文件

- `selected_post_36.csv`：便于人工核对的冻结清单。
- `selected_post_36.json`：前端/实验脚本使用的完整 post manifest。
- `pre_sources_18.csv`：18 个 source pre SCC 的概要映射。
- `pre_sources_18.json`：未注入 pre 文本、节点和内部边。
- `post_materials_36_internal.json`：按冻结注入规则重建的 36 个 post 纯文本材料；旧 12 个逐节点文本已与旧专家包精确核对。
- `master_manifest.json`：前端消费入口；本轮只筛选 `annotation_action=new_annotation`，内部 pre/post 映射与复用状态保留在该文件中。
- `selection_validation.json`：平衡、复用、U、hash 与验证证明。
- `select_candidates.py`：可复现生成脚本。

复现：在仓库根目录执行 `python 2026NAACL/SA-MCGS/annotation_prep/candidates/select_candidates.py`。
"""
    (SCRIPT_DIR / "README.md").write_text(report, encoding="utf-8")


def main() -> None:
    all_rows = load_case_plan()
    legal_pool = [row for row in all_rows if row["domain"] in DOMAINS]
    if len(legal_pool) != 72:
        raise AssertionError(f"expected 72 legal post cases, found {len(legal_pool)}")
    legacy_rows = load_legacy_cases()
    legacy, legacy_map = match_legacy_cases(legal_pool, legacy_rows)
    selected, domain_breadth = choose_global_sample(legal_pool, legacy)
    pre_sources, graphs = build_pre_sources(selected)
    post_materials, legacy_text_matches = build_post_materials(
        selected, legacy_map, graphs
    )
    validation = validate_selection(
        legal_pool,
        selected,
        legacy_map,
        pre_sources,
        legacy_text_matches,
    )
    validation["maximum_source_breadth_by_domain"] = domain_breadth
    write_outputs(
        selected,
        legacy_map,
        pre_sources,
        post_materials,
        validation,
    )
    print(
        json.dumps(
            {
                "selected": validation["selected_post_cases"],
                "legacy": validation["legacy_post_cases_reused"],
                "U": validation["selected_source_physical_sccs_U"],
                "domain": validation["domain_counts"],
                "template": validation["template_counts"],
                "size_bins": validation["size_bin_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
