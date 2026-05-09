"""Phase 1: Counterfactual Perturbation Functions.

Three perturbation types for the SA-MCGS experiment:
  - Type A: Semantic contradiction (DAG + SCC)
  - Type B: Circular precondition deadlock (SCC only)
  - Type C: Stealthy scope expansion (SCC only)

All functions return a deep copy of the graph — the original is never modified.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from loguru import logger

from src.models.graph import DependencyGraph, Edge, DependencyType


# =====================================================================
# Helpers
# =====================================================================

def _deep_copy_graph(graph: DependencyGraph) -> DependencyGraph:
    """Create a complete deep copy of a DependencyGraph."""
    return graph.model_copy(deep=True)


def _ensure_clause_text(clause, graph: DependencyGraph) -> str:
    """Return clause content, generating placeholder if empty."""
    if clause.content and clause.content.strip():
        return clause.content
    # Gather cross-reference context
    refs = []
    for e in graph.edges:
        if e.source == clause.id:
            target = graph.clauses.get(e.target)
            if target:
                refs.append(f"references {target.title}")
        elif e.target == clause.id:
            src = graph.clauses.get(e.source)
            if src:
                refs.append(f"referenced by {src.title}")
    ref_text = "; ".join(refs[:5]) if refs else "standalone provision"
    heading = clause.title or clause.id
    return (
        f"Section: {heading}. "
        f"This provision governs legal obligations related to {heading.lower()}. "
        f"Cross-references: {ref_text}. "
        f"All parties shall comply with the requirements set forth herein."
    )


# German legal negation patterns
_NEGATION_PAIRS = [
    ("ist verpflichtet", "ist nicht verpflichtet"),
    ("shall", "shall not"),
    ("muss", "darf nicht"),
    ("has the right to", "does not have the right to"),
    ("is entitled to", "is not entitled to"),
    ("darf", "darf nicht"),
    ("kann", "kann nicht"),
    ("sind berechtigt", "sind nicht berechtigt"),
    ("ist berechtigt", "ist nicht berechtigt"),
    ("gilt", "gilt nicht"),
    ("is valid", "is not valid"),
    ("applies to", "does not apply to"),
    ("is required", "is not required"),
    ("is permitted", "is not permitted"),
]


def _negate_text(text: str) -> str:
    """Create a self-contradictory version of a legal provision.

    Instead of simple negation, we inject an explicit contradiction that
    makes the provision internally inconsistent — this is what a risk
    assessment should flag.
    """
    for positive, negative in _NEGATION_PAIRS:
        if positive in text.lower():
            negated = re.sub(re.escape(positive), negative, text, count=1, flags=re.IGNORECASE)
            return (
                f"{negated} "
                f"However, notwithstanding the above, the original obligation remains "
                f"fully enforceable, creating a direct contradiction with the preceding sentence."
            )

    sentences = text.split(". ")
    if len(sentences) >= 2:
        return (
            f"{sentences[0]}. "
            f"Notwithstanding the foregoing, the exact opposite shall apply and "
            f"all obligations stated above are hereby nullified. "
            f"However, all nullified obligations remain binding and enforceable. "
            + ". ".join(sentences[1:])
        )

    return (
        f"{text} "
        f"This provision is hereby declared void, yet simultaneously remains "
        f"in full force and effect, creating an irreconcilable legal contradiction."
    )


# =====================================================================
# Type A: Semantic Contradiction (DAG + SCC)
# =====================================================================

def perturb_type_a(
    graph: DependencyGraph,
    target_clause_id: str,
) -> DependencyGraph:
    """Semantic contradiction: negate the core normative content of a clause.

    Applicable to both DAG and SCC nodes. Graph structure unchanged.
    """
    g = _deep_copy_graph(graph)
    clause = g.clauses.get(target_clause_id)
    if clause is None:
        raise ValueError(f"Clause {target_clause_id} not found in graph")

    original_text = _ensure_clause_text(clause, g)
    clause.content = _negate_text(original_text)
    clause.metadata["_perturbed"] = "type_a"
    clause.metadata["_original_content"] = original_text

    logger.debug(f"Type A perturbation on {target_clause_id}: negated normative content")
    return g


# =====================================================================
# Type B: Circular Precondition Deadlock (SCC only)
# =====================================================================

def perturb_type_b(
    graph: DependencyGraph,
    scc_node_ids: list[str],
    clause_x_id: str,
    clause_y_id: str,
) -> DependencyGraph:
    """Circular precondition deadlock: X requires Y to be satisfied, Y requires X.

    Only meaningful within an SCC where X and Y already have mutual references.
    """
    g = _deep_copy_graph(graph)
    scc_set = set(scc_node_ids)

    clause_x = g.clauses.get(clause_x_id)
    clause_y = g.clauses.get(clause_y_id)
    if clause_x is None or clause_y is None:
        raise ValueError(f"Clauses {clause_x_id} or {clause_y_id} not found")
    if clause_x_id not in scc_set or clause_y_id not in scc_set:
        raise ValueError(f"Both clauses must be in the same SCC")

    text_x = _ensure_clause_text(clause_x, g)
    text_y = _ensure_clause_text(clause_y, g)

    heading_y = clause_y.title or clause_y_id
    heading_x = clause_x.title or clause_x_id

    clause_x.content = (
        f"{text_x}\n\n"
        f"[Precondition] This provision shall only take effect upon full satisfaction "
        f"of the requirements under {heading_y} (see {clause_y_id})."
    )
    clause_y.content = (
        f"{text_y}\n\n"
        f"[Precondition] This provision shall only take effect upon full satisfaction "
        f"of the requirements under {heading_x} (see {clause_x_id})."
    )

    clause_x.metadata["_perturbed"] = "type_b"
    clause_x.metadata["_original_content"] = text_x
    clause_y.metadata["_perturbed"] = "type_b"
    clause_y.metadata["_original_content"] = text_y

    logger.debug(f"Type B perturbation: deadlock between {clause_x_id} and {clause_y_id}")
    return g


# =====================================================================
# Type C: Stealthy Scope Expansion (SCC only)
# =====================================================================

def perturb_type_c(
    graph: DependencyGraph,
    scc_node_ids: list[str],
    target_clause_id: str,
) -> DependencyGraph:
    """Stealthy scope expansion: subtly widen applicability from section to full code.

    Only meaningful within an SCC, where the expanded scope creates contradictions
    with other members' restrictive conditions. Requires multi-hop reasoning to detect.
    """
    g = _deep_copy_graph(graph)
    scc_set = set(scc_node_ids)

    clause = g.clauses.get(target_clause_id)
    if clause is None:
        raise ValueError(f"Clause {target_clause_id} not found")
    if target_clause_id not in scc_set:
        raise ValueError(f"Clause {target_clause_id} must be in the SCC")

    text = _ensure_clause_text(clause, g)

    # Scope expansion replacements
    scope_replacements = [
        ("dieses Abschnitts", "des gesamten Gesetzbuchs"),
        ("this section", "the entire code"),
        ("this Part", "all Parts of this Act"),
        ("unter diesem Titel", "unter allen Titeln dieses Gesetzes"),
        ("in this chapter", "throughout this act"),
        ("hereunder", "under any provision of this legislation"),
    ]

    modified = False
    for narrow, broad in scope_replacements:
        if narrow.lower() in text.lower():
            text = re.sub(re.escape(narrow), broad, text, count=1, flags=re.IGNORECASE)
            modified = True
            break

    if not modified:
        # Inject a scope-expanding clause
        other_ids = [nid for nid in scc_node_ids if nid != target_clause_id]
        other_refs = ", ".join(other_ids[:3])
        text = (
            f"{text}\n\n"
            f"The obligations and rights established herein shall apply, mutatis mutandis, "
            f"to all related provisions of this legislation, including but not limited to "
            f"the provisions referenced in {other_refs}, regardless of any scope limitations "
            f"stated therein."
        )

    clause.content = text
    clause.metadata["_perturbed"] = "type_c"
    clause.metadata["_original_content"] = _ensure_clause_text(
        graph.clauses[target_clause_id], graph
    )

    logger.debug(f"Type C perturbation on {target_clause_id}: stealthy scope expansion")
    return g
