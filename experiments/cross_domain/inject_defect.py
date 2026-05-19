"""Unified Defect Injection Protocol (UDIP) for cross-domain SA-MCGS evaluation.

Injection types aligned with experiments/perturbation.py:
  - Type A (semantic contradiction): node content contradicts its structural role
  - Type B (circular lock): node is the unresolvable lock point in the SCC

Literature basis:
  - DOMINANT (SDM'19), CoLA (TNNLS'22): standard attribute injection protocol
  - DVGraph (ICSE'22): CVE propagation in dependency graphs
  - CLAUSE Benchmark (EACL'26): semantic contradiction injection
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.perturbation import _deep_copy_graph
from src.models.graph import DependencyGraph, SCCInfo


DOMAIN_INJECT_TYPE = {
    "debian": "type_b_cross",
    "wikipedia": "type_a_cross",
    "sec_ex21": "type_b_cross",
    "bgb": "type_b_cross",
    "cuad": "type_b_cross",
}

SUPPORTED_INJECT_PROFILES = {"explicit", "memory_stress"}
STRUCTURAL_MEMORY_PROFILE_VERSION = "structural_simple_v2"
DEFAULT_MEMORY_CONFLICT_TEMPLATE = "handoff_invariant"
DEFAULT_MEMORY_CONFLICT_SEVERITY = "standard"
SUPPORTED_MEMORY_CONFLICT_TEMPLATES = {
    "direct_mutex",
    "handoff_invariant",
    "temporal_gate",
    "condition_trigger",
}
SUPPORTED_MEMORY_CONFLICT_SEVERITIES = {"standard", "severe", "critical"}
MEMORY_CONFLICT_DIFFICULTY = {
    "direct_mutex": "obvious",
    "handoff_invariant": "moderate",
    "temporal_gate": "subtle",
    "condition_trigger": "hard",
}
MEMORY_CONFLICT_SEVERITY_LABEL = {
    "standard": "baseline",
    "severe": "high_impact",
    "critical": "high_impact_no_fallback",
}


def _make_content_debian(pkg_title: str, others: list[str], n: int) -> str:
    """Type B: Circular lock point (CVE propagation hub). CVSS 3.1 format."""
    others_str = ", ".join(others[:5])
    return (
        f"[DEFECT TYPE-B: Circular Dependency Lock] Package {pkg_title} has been "
        f"identified as the critical lock point in this circular dependency cluster. "
        f"Due to circular version constraints with {others_str}, this package creates "
        f"an unresolvable bootstrapping deadlock: no package in the cycle can be "
        f"updated without first resolving {pkg_title}, yet {pkg_title} itself requires "
        f"all co-dependent packages to be updated simultaneously. "
        f"CVSS 3.1 Base Score: 8.1 HIGH (AV:N/AC:H/PR:N/UI:N/S:C/C:H/I:H/A:L). "
        f"Root cause: {pkg_title} acts as the circular version lock; all {n} packages "
        f"in this SCC ({others_str}) cannot be independently updated until this "
        f"circular dependency is resolved. This is the primary CVE propagation vector "
        f"for the entire cluster (ref: DVGraph, ICSE 2022)."
    )


def _make_content_wikipedia(cat_title: str, others: list[str], n: int) -> str:
    """Type A: Semantic contradiction (category is simultaneously parent and child)."""
    others_str = ", ".join(others[:4])
    return (
        f"[DEFECT TYPE-A: Ontological Contradiction] Wikipedia category \"{cat_title}\" "
        f"has been identified as the most likely misplaced category in this cycle. "
        f"This category is simultaneously classified as a subcategory of nodes in "
        f"the cycle ({others_str}) AND as an ancestor of those same nodes through "
        f"the cyclic path, creating an ontological contradiction: a category cannot "
        f"logically be both a descendant and an ancestor of the same concept. "
        f"According to Wikipedia's WP:CYCLE policy, category hierarchies must form "
        f"a directed acyclic graph (DAG). This category's placement violates that "
        f"invariant and is the most likely candidate for removal to break the cycle. "
        f"The cycle involves {n} categories total: {cat_title}, {others_str}."
    )


def _make_content_sec(entity_title: str, others: list[str], n: int) -> str:
    """Type B: Circular ownership lock (anomalous special-purpose vehicle)."""
    others_str = ", ".join(others[:4])
    return (
        f"[DEFECT TYPE-B: Circular Ownership Lock] Entity \"{entity_title}\" has been "
        f"identified as the most likely anomalous node causing circular ownership in "
        f"this SEC Exhibit 21 filing cluster. This entity is simultaneously recorded "
        f"as a controlling shareholder of subsidiaries in the chain ({others_str}) "
        f"AND is itself controlled by entities within the same ownership chain, "
        f"creating a circular ownership structure that violates SEC Regulation S-X "
        f"requirements for consolidated financial statement preparation. "
        f"This pattern is consistent with a special-purpose vehicle (SPV) or "
        f"shell company used for tax optimization or regulatory arbitrage. "
        f"The circular ownership involves {n} entities total. "
        f"Resolving this filing error requires removing or restructuring "
        f"\"{entity_title}\"'s ownership links to break the cycle."
    )


def _make_content_legal(record_title: str, others: list[str], n: int) -> str:
    """Explicit diagnostic content for legal/contract records."""
    others_str = ", ".join(others[:4])
    return (
        f"[DEFECT TYPE-B: Circular Legal Condition] Record \"{record_title}\" is "
        f"marked as the central lock point in this legal dependency cycle. It "
        f"conditions enforceability on related records ({others_str}) while those "
        f"records rely on this record to become operative first, creating an "
        f"unresolvable circular condition across {n} interdependent records."
    )


_CONTENT_BUILDERS = {
    "debian": _make_content_debian,
    "wikipedia": _make_content_wikipedia,
    "sec_ex21": _make_content_sec,
    "bgb": _make_content_legal,
    "cuad": _make_content_legal,
}


def _ordered_scc_ids(graph: DependencyGraph, scc: SCCInfo) -> list[str]:
    """Return a deterministic cycle-like order for chain-style injections."""
    scc_ids = set(scc.clause_ids)
    edges = [
        e for e in (scc.internal_edges or graph.edges)
        if e.source in scc_ids and e.target in scc_ids
    ]
    adjacency: dict[str, list[str]] = {cid: [] for cid in scc.clause_ids}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append(edge.target)
    for neighbors in adjacency.values():
        neighbors.sort()

    start = sorted(scc.clause_ids)[0]
    ordered = [start]
    seen = {start}
    current = start
    while len(ordered) < len(scc.clause_ids):
        next_nodes = [nid for nid in adjacency.get(current, []) if nid not in seen]
        if not next_nodes:
            break
        current = next_nodes[0]
        ordered.append(current)
        seen.add(current)

    ordered.extend(cid for cid in sorted(scc.clause_ids) if cid not in seen)
    return ordered


def _pick_witness(ordered_ids: list[str], target_id: str) -> tuple[str, int]:
    """Choose an existing SCC node far from the injected root."""
    n = len(ordered_ids)
    if n < 2:
        raise ValueError("memory_stress injection requires an SCC with at least two nodes")
    target_idx = ordered_ids.index(target_id)
    offset = max(1, n // 2)
    witness_id = ordered_ids[(target_idx + offset) % n]
    if witness_id == target_id:
        witness_id = ordered_ids[(target_idx + 1) % n]
        offset = 1
    return witness_id, offset


def _node_at_offset(ordered_ids: list[str], target_id: str, offset: int) -> str:
    target_idx = ordered_ids.index(target_id)
    return ordered_ids[(target_idx + offset) % len(ordered_ids)]


def _pick_bridge(
    ordered_ids: list[str],
    target_id: str,
    witness_id: str,
    witness_distance: int,
) -> tuple[str | None, int | None]:
    """Choose a middle evidence node between root and witness when available."""
    if len(ordered_ids) < 3:
        return None, None
    offset = max(1, witness_distance // 2)
    bridge_id = _node_at_offset(ordered_ids, target_id, offset)
    if bridge_id in {target_id, witness_id}:
        for candidate in ordered_ids:
            if candidate not in {target_id, witness_id}:
                bridge_id = candidate
                offset = (ordered_ids.index(candidate) - ordered_ids.index(target_id)) % len(ordered_ids)
                break
    return bridge_id, offset


def _pick_affected_nodes(
    ordered_ids: list[str],
    anchors: list[str],
    excluded: set[str],
) -> list[str]:
    """Pick unchanged downstream nodes that may reasonably be ranked as impacted."""
    affected: list[str] = []
    for anchor in anchors:
        if anchor not in ordered_ids:
            continue
        start = ordered_ids.index(anchor)
        for hop in range(1, min(len(ordered_ids), 4)):
            candidate = ordered_ids[(start + hop) % len(ordered_ids)]
            if candidate not in excluded and candidate not in affected:
                affected.append(candidate)
                break
    return affected[:2]


def _make_structural_simple_contents(
    domain: str,
    conflict_template: str,
    target_title: str,
    witness_title: str,
    bridge_title: str | None,
) -> dict[str, str]:
    """Return target/bridge/witness text for structural conflict suites."""
    bridge_title = bridge_title or "the intermediate record"
    if domain == "debian":
        if conflict_template == "direct_mutex":
            return {
                "target": (
                    f"Record for {target_title}. During the migration window this package keeps "
                    "the legacy ABI available for dependents until the release team signs off "
                    "on the final transition note. Downstream records must continue to treat "
                    "the legacy ABI as the required interface while the window remains open."
                ),
                "witness": (
                    f"Record for {witness_title}. This package may complete configuration only "
                    f"after {target_title} exposes the new ABI as the required interface. If the "
                    "legacy ABI is still required, this package must wait."
                ),
                "template": "debian_direct_legacy_vs_new_abi",
            }
        if conflict_template == "temporal_gate":
            return {
                "target": (
                    f"Record for {target_title}. The transition receipt is scheduled after the "
                    "configuration freeze. Before that receipt is posted, dependents should keep "
                    "using the prior interface classification for release planning."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This handoff record forwards the receipt status "
                    "from the upstream package without changing the date. Downstream activation "
                    "notes are expected to use the same receipt status seen here."
                ),
                "witness": (
                    f"Record for {witness_title}. The activation note is filed as if the transition "
                    "receipt had already arrived before the freeze, and the package is scheduled "
                    "on that completed-transition basis."
                ),
                "template": "debian_temporal_receipt_gate",
            }
        if conflict_template == "condition_trigger":
            return {
                "target": (
                    f"Record for {target_title}. The new interface may become the planning basis "
                    "only after two independent compatibility notes are published. This record "
                    "lists one note as staged and leaves the second note open."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This relay preserves the compatibility condition "
                    "exactly as received. A staged note is not treated here as a completed pair of "
                    "compatibility notes."
                ),
                "witness": (
                    f"Record for {witness_title}. The local configuration assumes the compatibility "
                    "condition has been satisfied and proceeds on the new-interface planning basis."
                ),
                "template": "debian_condition_trigger_partial_compatibility",
            }
        return {
            "target": (
                f"Record for {target_title}. The outbound handoff from this package remains in the "
                "legacy interface class for the current migration window. This entry does not act "
                "as a conversion point."
            ),
            "bridge": (
                f"Record for {bridge_title}. This middle handoff receives the interface class from "
                "the upstream side and forwards the same class unchanged. It is a pass-through "
                "maintenance record, not a reinterpretation step."
            ),
            "witness": (
                f"Record for {witness_title}. This package can finish configuration only when the "
                "handoff it receives is already in the new interface class."
            ),
            "template": "debian_handoff_invariant_abi_class",
        }
    if domain == "wikipedia":
        if conflict_template == "direct_mutex":
            return {
                "target": (
                    f"Record for {target_title}. This category branch is reserved for current "
                    "or active entries. Pages passed through this branch should describe items "
                    "that are ongoing, living, active, or currently maintained."
                ),
                "witness": (
                    f"Record for {witness_title}. Entries received from the same branch are "
                    "accepted here only when they are former, historical, inactive, or no longer "
                    "maintained."
                ),
                "template": "wikipedia_direct_active_vs_inactive",
            }
        if conflict_template == "temporal_gate":
            return {
                "target": (
                    f"Record for {target_title}. The branch retains the current-status label until "
                    "a closing source is recorded. The maintenance note says no closing source has "
                    "been attached for this path."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This category relay carries the lifecycle label "
                    "from the incoming branch without adding a separate closing source."
                ),
                "witness": (
                    f"Record for {witness_title}. Pages arriving through this path are handled as "
                    "closed historical entries in the archive queue."
                ),
                "template": "wikipedia_temporal_closing_source_gate",
            }
        if conflict_template == "condition_trigger":
            return {
                "target": (
                    f"Record for {target_title}. A page may move from current to historical status "
                    "only after an explicit closing source is cited. This branch note says the "
                    "source field is still blank."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This relay preserves the cited-source status from "
                    "the incoming branch and does not infer a closing source from routine cleanup."
                ),
                "witness": (
                    f"Record for {witness_title}. The receiving category treats the same incoming "
                    "pages as historical because they appeared in a cleanup batch."
                ),
                "template": "wikipedia_condition_trigger_missing_source",
            }
        return {
            "target": (
                f"Record for {target_title}. The incoming branch is maintained as current-status "
                "material. Items on this path are not relabeled while this entry is active."
            ),
            "bridge": (
                f"Record for {bridge_title}. This intermediate category inherits the lifecycle "
                "label from the incoming branch and forwards that label unchanged."
            ),
            "witness": (
                f"Record for {witness_title}. This receiving category accepts the branch only as "
                "historical or inactive material."
            ),
            "template": "wikipedia_handoff_invariant_lifecycle_label",
        }
    if domain == "sec_ex21":
        if conflict_template == "direct_mutex":
            return {
                "target": (
                    f"Record for {target_title}. For this consolidation path, the entity is treated "
                    "as fully consolidated by the upstream registrant. The note states that no "
                    "separate non-controlling interest is retained for this path."
                ),
                "witness": (
                    f"Record for {witness_title}. The same consolidation path reserves a 20 percent "
                    "non-controlling interest for the downstream schedule."
                ),
                "template": "sec_direct_full_consolidation_vs_retained_interest",
            }
        if conflict_template == "temporal_gate":
            return {
                "target": (
                    f"Record for {target_title}. The ownership change is approved after quarter close. "
                    "For the quarter-close schedule, this path remains under the prior full-control "
                    "basis."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This register entry carries the quarter-close basis "
                    "from the upstream schedule without changing the effective date."
                ),
                "witness": (
                    f"Record for {witness_title}. The downstream worksheet records a retained minority "
                    "interest as effective inside the same quarter-close schedule."
                ),
                "template": "sec_temporal_quarter_close_gate",
            }
        if conflict_template == "condition_trigger":
            return {
                "target": (
                    f"Record for {target_title}. A retained outside interest may be recognized only "
                    "after a control amendment is filed. This entry states that the amendment has not "
                    "been filed for the current consolidation path."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This intermediate register carries the amendment "
                    "status exactly as received and does not convert an internal worksheet into a "
                    "filed amendment."
                ),
                "witness": (
                    f"Record for {witness_title}. The ownership worksheet reserves a 20 percent "
                    "outside interest for the same consolidation path."
                ),
                "template": "sec_condition_trigger_unfiled_amendment",
            }
        return {
            "target": (
                f"Record for {target_title}. This path is carried on a full-control basis, and the "
                "entry does not record a carve-out or partial disposal."
            ),
            "bridge": (
                f"Record for {bridge_title}. This intermediate entity forwards the same control basis "
                "from the upstream schedule and does not introduce a separate carve-out."
            ),
            "witness": (
                f"Record for {witness_title}. The downstream schedule reserves a 20 percent outside "
                "interest on the same path."
            ),
            "template": "sec_handoff_invariant_control_basis",
        }
    if domain == "bgb":
        if conflict_template == "direct_mutex":
            return {
                "target": (
                    f"Record for {target_title}. A party that cures the stated obligation within "
                    "three months is treated as timely and faces no additional burden on this path."
                ),
                "witness": (
                    f"Record for {witness_title}. The same path requires a party that cures within "
                    "three months to pay an additional 20 percent charge before the cure is accepted."
                ),
                "template": "bgb_direct_timely_cure_vs_extra_charge",
            }
        if conflict_template == "temporal_gate":
            return {
                "target": (
                    f"Record for {target_title}. The grace period remains open until the three-month "
                    "deadline expires. Before that date, the obligation is handled as timely cured."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This reference carries the grace-period status "
                    "forward without changing the deadline or adding a separate trigger."
                ),
                "witness": (
                    f"Record for {witness_title}. The downstream remedy is applied as if the "
                    "three-month deadline had already expired on the same path."
                ),
                "template": "bgb_temporal_grace_period_gate",
            }
        if conflict_template == "condition_trigger":
            return {
                "target": (
                    f"Record for {target_title}. A supplementary payment becomes due only after "
                    "formal notice has been served and the cure period has expired. This record "
                    "states that notice is still pending."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This reference preserves the notice status and "
                    "does not convert a pending notice into a served notice."
                ),
                "witness": (
                    f"Record for {witness_title}. The downstream remedy applies the supplementary "
                    "payment immediately on the same obligation path."
                ),
                "template": "bgb_condition_trigger_pending_notice",
            }
        return {
            "target": (
                f"Record for {target_title}. The obligation remains in the ordinary cure class for "
                "this reference path, and no surcharge is introduced by this provision."
            ),
            "bridge": (
                f"Record for {bridge_title}. This intermediate reference forwards the same cure "
                "class unchanged and does not reinterpret the remedy."
            ),
            "witness": (
                f"Record for {witness_title}. The receiving provision applies the same path only "
                "after it has been moved into a surcharge remedy class."
            ),
            "template": "bgb_handoff_invariant_cure_class",
        }
    if domain == "cuad":
        if conflict_template == "direct_mutex":
            return {
                "target": (
                    f"Record for {target_title}. The customer may terminate for convenience on "
                    "30 days notice without paying any early termination fee on this path."
                ),
                "witness": (
                    f"Record for {witness_title}. The same termination path requires payment of "
                    "an early termination fee before the 30 day notice can become effective."
                ),
                "template": "cuad_direct_no_fee_vs_fee",
            }
        if conflict_template == "temporal_gate":
            return {
                "target": (
                    f"Record for {target_title}. The notice period starts only when written notice "
                    "is received. Until receipt, no termination clock is running."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This cross-reference passes through the receipt "
                    "status without changing the notice date."
                ),
                "witness": (
                    f"Record for {witness_title}. The downstream clause treats the termination "
                    "clock as already running before written notice is received."
                ),
                "template": "cuad_temporal_notice_receipt_gate",
            }
        if conflict_template == "condition_trigger":
            return {
                "target": (
                    f"Record for {target_title}. The payment obligation is excused only if an audit "
                    "exception is confirmed in writing. This record says the exception is still "
                    "under review."
                ),
                "bridge": (
                    f"Record for {bridge_title}. This reference carries the audit status as under "
                    "review and does not treat review as written confirmation."
                ),
                "witness": (
                    f"Record for {witness_title}. The downstream payment clause already applies "
                    "the excuse as if written confirmation had been issued."
                ),
                "template": "cuad_condition_trigger_unconfirmed_exception",
            }
        return {
            "target": (
                f"Record for {target_title}. The obligation is forwarded as an unconditional "
                "payment duty for this path."
            ),
            "bridge": (
                f"Record for {bridge_title}. This intermediate clause forwards the same payment "
                "status unchanged and does not introduce a condition."
            ),
            "witness": (
                f"Record for {witness_title}. The receiving clause treats the same payment path as "
                "conditional on a later approval."
            ),
            "template": "cuad_handoff_invariant_payment_status",
        }
    if conflict_template == "direct_mutex":
        return {
            "target": (
                f"Record for {target_title}. For this consolidation path, the entity is treated "
                "as fully consolidated by the upstream registrant. The note states that no "
                "separate non-controlling interest is retained for this path."
            ),
            "witness": (
                f"Record for {witness_title}. The same consolidation path reserves a 20 percent "
                "non-controlling interest for the downstream schedule."
            ),
            "template": "sec_direct_full_consolidation_vs_retained_interest",
        }
    if conflict_template == "temporal_gate":
        return {
            "target": (
                f"Record for {target_title}. The ownership change is approved after quarter close. "
                "For the quarter-close schedule, this path remains under the prior full-control "
                "basis."
            ),
            "bridge": (
                f"Record for {bridge_title}. This register entry carries the quarter-close basis "
                "from the upstream schedule without changing the effective date."
            ),
            "witness": (
                f"Record for {witness_title}. The downstream worksheet records a retained minority "
                "interest as effective inside the same quarter-close schedule."
            ),
            "template": "sec_temporal_quarter_close_gate",
        }
    if conflict_template == "condition_trigger":
        return {
            "target": (
                f"Record for {target_title}. A retained outside interest may be recognized only "
                "after a control amendment is filed. This entry states that the amendment has not "
                "been filed for the current consolidation path."
            ),
            "bridge": (
                f"Record for {bridge_title}. This intermediate register carries the amendment "
                "status exactly as received and does not convert an internal worksheet into a "
                "filed amendment."
            ),
            "witness": (
                f"Record for {witness_title}. The ownership worksheet reserves a 20 percent "
                "outside interest for the same consolidation path."
            ),
            "template": "sec_condition_trigger_unfiled_amendment",
        }
    return {
        "target": (
            f"Record for {target_title}. This path is carried on a full-control basis, and the "
            "entry does not record a carve-out or partial disposal."
        ),
        "bridge": (
            f"Record for {bridge_title}. This intermediate entity forwards the same control basis "
            "from the upstream schedule and does not introduce a separate carve-out."
        ),
        "witness": (
            f"Record for {witness_title}. The downstream schedule reserves a 20 percent outside "
            "interest on the same path."
        ),
        "template": "sec_handoff_invariant_control_basis",
    }


def _strip_record_prefix(note: str, title: str | None) -> str:
    if not title:
        return note
    prefix = f"Record for {title}. "
    return note[len(prefix):] if note.startswith(prefix) else note


def _severity_suffixes(domain: str, severity: str) -> dict[str, str]:
    """Return consequence notes for high-severity structural conflicts."""
    if severity == "standard":
        return {}
    if domain == "cuad":
        if severity == "critical":
            return {
                "target": (
                    "This status is non-waivable on the same transaction path. A contrary "
                    "downstream treatment leaves no cure window, automatically suspends "
                    "performance, accelerates all unpaid amounts, and triggers termination "
                    "without further notice."
                ),
                "bridge": (
                    "The pass-through status is binding for the same transaction path and may "
                    "not be silently converted by a later clause without a signed amendment."
                ),
                "witness": (
                    "This record makes the opposite status immediately operative on that same "
                    "path and treats any upstream mismatch as a material default with payment "
                    "acceleration and loss of cure rights."
                ),
            }
        return {
            "target": (
                "This status is binding for the same transaction path. A contrary downstream "
                "treatment causes immediate suspension of performance and accelerates unpaid "
                "amounts unless a written amendment resolves the path."
            ),
            "bridge": (
                "The pass-through status is binding and cannot be reclassified by routine "
                "cross-reference handling."
            ),
            "witness": (
                "This record treats the opposite status as immediately operative on the same "
                "path and triggers material default consequences if the upstream status differs."
            ),
        }
    if domain == "bgb":
        if severity == "critical":
            return {
                "target": (
                    "This classification is mandatory for the same obligation path. A contrary "
                    "downstream treatment would make the same debtor both released from the "
                    "burden and immediately in default, with no residual discretion to reconcile "
                    "the two remedies."
                ),
                "bridge": (
                    "The reference preserves this mandatory classification and does not create "
                    "an independent trigger that can reverse the remedy class."
                ),
                "witness": (
                    "This record applies the opposite remedy class immediately on the same "
                    "obligation path, creating a non-curable enforcement conflict if the upstream "
                    "classification is still in force."
                ),
            }
        return {
            "target": (
                "This classification controls the same obligation path. A contrary downstream "
                "treatment would make the same performance both timely cured and surchargeable."
            ),
            "bridge": (
                "The reference keeps the classification fixed and does not create a new trigger."
            ),
            "witness": (
                "This record applies the opposite remedy class on the same obligation path and "
                "treats the mismatch as enforceable immediately."
            ),
        }
    if severity == "critical":
        return {
            "target": (
                "This state is mandatory for the same dependency path. A contrary downstream "
                "state leaves no valid fallback and makes the same record simultaneously allowed "
                "and barred."
            ),
            "bridge": (
                "The intermediate record forwards the mandatory state without creating an "
                "independent conversion point."
            ),
            "witness": (
                "This record applies the opposite state immediately on the same path and treats "
                "the mismatch as a blocking inconsistency."
            ),
        }
    return {
        "target": (
            "This state is binding for the same dependency path and must be preserved by "
            "downstream records."
        ),
        "bridge": (
            "The intermediate record preserves the state and does not reclassify it."
        ),
        "witness": (
            "This record applies the opposite state on the same dependency path and treats the "
            "mismatch as immediately operative."
        ),
    }


def _apply_conflict_severity(
    contents: dict[str, str],
    domain: str,
    severity: str,
) -> dict[str, str]:
    if severity not in SUPPORTED_MEMORY_CONFLICT_SEVERITIES:
        raise ValueError(
            f"Unknown memory-stress conflict severity: {severity}. "
            f"Must be one of {sorted(SUPPORTED_MEMORY_CONFLICT_SEVERITIES)}"
        )
    if severity == "standard":
        return contents
    updated = dict(contents)
    suffixes = _severity_suffixes(domain, severity)
    for role, suffix in suffixes.items():
        if role in updated and suffix:
            updated[role] = f"{updated[role]} {suffix}"
    updated["template"] = f"{updated.get('template', 'structural_conflict')}_{severity}"
    return updated


def _append_minimal_perturbation(original: str, note: str) -> str:
    original = (original or "").strip()
    note = note.strip()
    if not original:
        return note
    return f"{original}\n\n{note}"


def _apply_structural_memory_stress(
    graph: DependencyGraph,
    scc: SCCInfo,
    domain: str,
    target_id: str,
    conflict_template: str = DEFAULT_MEMORY_CONFLICT_TEMPLATE,
    conflict_severity: str = DEFAULT_MEMORY_CONFLICT_SEVERITY,
) -> dict[str, str | int | list[str]]:
    """Inject a simple target/witness conflict using only existing SCC nodes."""
    if conflict_template not in SUPPORTED_MEMORY_CONFLICT_TEMPLATES:
        raise ValueError(
            f"Unknown memory-stress conflict template: {conflict_template}. "
            f"Must be one of {sorted(SUPPORTED_MEMORY_CONFLICT_TEMPLATES)}"
        )
    if conflict_severity not in SUPPORTED_MEMORY_CONFLICT_SEVERITIES:
        raise ValueError(
            f"Unknown memory-stress conflict severity: {conflict_severity}. "
            f"Must be one of {sorted(SUPPORTED_MEMORY_CONFLICT_SEVERITIES)}"
        )
    ordered_ids = _ordered_scc_ids(graph, scc)
    witness_id, witness_distance = _pick_witness(ordered_ids, target_id)
    bridge_id, bridge_distance = _pick_bridge(ordered_ids, target_id, witness_id, witness_distance)
    target = graph.clauses.get(target_id)
    witness = graph.clauses.get(witness_id)
    if target is None or witness is None:
        raise ValueError(f"Cannot find target/witness nodes: {target_id}, {witness_id}")
    bridge = graph.clauses.get(bridge_id) if bridge_id else None
    use_bridge = conflict_template != "direct_mutex" and bridge is not None

    target.metadata.setdefault("_original_content", target.content or f"Node: {target.title}")
    witness.metadata.setdefault("_original_content", witness.content or f"Node: {witness.title}")
    target.metadata["_inject_simple_role"] = "target"
    witness.metadata["_inject_simple_role"] = "witness"
    if use_bridge:
        bridge.metadata.setdefault("_original_content", bridge.content or f"Node: {bridge.title}")
        bridge.metadata["_inject_simple_role"] = "bridge"

    contents = _make_structural_simple_contents(
        domain,
        conflict_template,
        target.title or target_id,
        witness.title or witness_id,
        bridge.title if bridge else None,
    )
    contents = _apply_conflict_severity(contents, domain, conflict_severity)
    target_note = _strip_record_prefix(contents["target"], target.title or target_id)
    witness_note = _strip_record_prefix(contents["witness"], witness.title or witness_id)
    target.content = _append_minimal_perturbation(target.metadata["_original_content"], target_note)
    witness.content = _append_minimal_perturbation(witness.metadata["_original_content"], witness_note)
    if use_bridge and "bridge" in contents:
        bridge_note = _strip_record_prefix(contents["bridge"], bridge.title if bridge else None)
        bridge.content = _append_minimal_perturbation(bridge.metadata["_original_content"], bridge_note)

    evidence_nodes = [target_id]
    if use_bridge and bridge_id:
        evidence_nodes.append(bridge_id)
    evidence_nodes.append(witness_id)
    risk_nodes = [target_id, witness_id]
    affected_nodes = _pick_affected_nodes(ordered_ids, risk_nodes, set(evidence_nodes))

    return {
        "witness_id": witness_id,
        "witness_distance": witness_distance,
        "bridge_id": bridge_id if use_bridge else None,
        "bridge_distance": bridge_distance if use_bridge else None,
        "risk_nodes": risk_nodes,
        "evidence_nodes": evidence_nodes,
        "affected_nodes": affected_nodes,
        "conflict_family": conflict_template,
        "conflict_difficulty": MEMORY_CONFLICT_DIFFICULTY[conflict_template],
        "conflict_severity": conflict_severity,
        "conflict_severity_label": MEMORY_CONFLICT_SEVERITY_LABEL[conflict_severity],
        "conflict_template": contents["template"],
        "ordered_ids": ordered_ids,
    }


def _make_structural_chain_content(
    domain: str,
    title: str,
    idx: int,
    n: int,
    prev_title: str,
    next_title: str,
    role: str,
) -> str:
    """Legacy chain note retained for reference; not used by memory_stress."""
    if domain == "debian":
        return (
            f"Debian package: {title}. Transition ledger node {idx + 1}/{n}. "
            f"It receives a handoff from {prev_title} and forwards the recorded state "
            f"to {next_title}. The local note describes ordinary release-engineering "
            "work and preserves the incoming handoff contract."
        )
    if domain == "wikipedia":
        return (
            f"Wikipedia category: {title}. Taxonomy ledger node {idx + 1}/{n}. "
            f"It receives a placement note from {prev_title} and forwards a record "
            f"toward {next_title}. The page text records ordinary maintenance."
        )
    return (
        f"SEC Exhibit 21 entity: {title}. Audit note {idx + 1}/{n}: this subsidiary "
        f"receives a consolidation note from {prev_title} and forwards the same record "
        f"toward {next_title}. The entry contains routine register maintenance."
    )


def inject_defect(
    graph: DependencyGraph,
    scc: SCCInfo,
    domain: str,
    seed: int = 42,
    profile: str = "explicit",
    conflict_template: str = DEFAULT_MEMORY_CONFLICT_TEMPLATE,
    conflict_severity: str = DEFAULT_MEMORY_CONFLICT_SEVERITY,
) -> tuple[DependencyGraph, str]:
    """Inject a realistic defect attribute into one reproducibly chosen SCC node.

    Uses the same metadata schema as experiments/perturbation.py so existing
    BGB/CUAD evaluation code can recognize injected nodes.
    """
    if domain not in _CONTENT_BUILDERS:
        raise ValueError(f"Unknown domain: {domain}. Must be one of {list(_CONTENT_BUILDERS)}")
    if profile not in SUPPORTED_INJECT_PROFILES:
        raise ValueError(f"Unknown injection profile: {profile}. Must be one of {sorted(SUPPORTED_INJECT_PROFILES)}")

    g = _deep_copy_graph(graph)

    random.seed(seed)
    sorted_ids = sorted(scc.clause_ids)
    if profile == "memory_stress":
        ordered_ids = _ordered_scc_ids(g, scc)
        later_third = ordered_ids[max(0, (len(ordered_ids) * 2) // 3):] or ordered_ids
        target_id = random.choice(later_third)
    else:
        target_id = random.choice(sorted_ids)
    others = [cid for cid in sorted_ids if cid != target_id]

    clause = g.clauses.get(target_id)
    if clause is None:
        raise ValueError(f"Node {target_id} not found in graph.clauses")

    orig_content = clause.content or f"Package: {clause.title}"
    if profile == "memory_stress":
        chain_info = _apply_structural_memory_stress(
            g, scc, domain, target_id,
            conflict_template=conflict_template,
            conflict_severity=conflict_severity,
        )
        new_content = clause.content
    else:
        builder = _CONTENT_BUILDERS[domain]
        chain_info = {}
        new_content = builder(clause.title, others, scc.size)

    clause.content = new_content
    clause.metadata["_perturbed"] = DOMAIN_INJECT_TYPE[domain]
    clause.metadata["_original_content"] = orig_content
    clause.metadata["_domain"] = domain
    clause.metadata["_inject_seed"] = seed
    clause.metadata["_inject_profile"] = profile
    if profile == "memory_stress":
        clause.metadata["_inject_profile_version"] = STRUCTURAL_MEMORY_PROFILE_VERSION
        clause.metadata["_inject_witness_node"] = chain_info.get("witness_id")
        clause.metadata["_inject_witness_distance"] = chain_info.get("witness_distance")
        clause.metadata["_inject_bridge_node"] = chain_info.get("bridge_id")
        clause.metadata["_inject_bridge_distance"] = chain_info.get("bridge_distance")
        clause.metadata["_inject_risk_nodes"] = chain_info.get("risk_nodes")
        clause.metadata["_inject_evidence_nodes"] = chain_info.get("evidence_nodes")
        clause.metadata["_inject_affected_nodes"] = chain_info.get("affected_nodes")
        clause.metadata["_inject_conflict_family"] = chain_info.get("conflict_family")
        clause.metadata["_inject_conflict_difficulty"] = chain_info.get("conflict_difficulty")
        clause.metadata["_inject_conflict_severity"] = chain_info.get("conflict_severity")
        clause.metadata["_inject_conflict_severity_label"] = chain_info.get("conflict_severity_label")
        clause.metadata["_inject_conflict_template"] = chain_info.get("conflict_template")

    return g, target_id


def get_injected_node(graph: DependencyGraph, scc: SCCInfo) -> str | None:
    """Scan SCC nodes to find which one, if any, was injected."""
    for node_id in scc.clause_ids:
        clause = graph.clauses.get(node_id)
        if clause and clause.metadata.get("_perturbed"):
            return node_id
    return None
