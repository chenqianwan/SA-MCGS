"""Small exact positive-Horn engine for the BGB Phase-1--3 smoke.

The module intentionally has no LLM or search dependency.  Its commit API
requires an execution receipt, so an unvisited window cannot silently enter the
knowledge base.  Semantics are finite, function-free and positive: failure to
derive a query is ``PR-Unknown``, never evidence for its negation.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identifier(value: Any, *, variable: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("symbol must be a string")
    value = value.strip()
    if variable and value.startswith("?"):
        body = value[1:]
        body = re.sub(r"[^\w]+", "_", body, flags=re.UNICODE).strip("_").lower()
        if not body:
            raise ValueError("empty variable")
        return f"?{body}"
    value = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE).strip("_").lower()
    if not value:
        raise ValueError("empty symbol")
    if value.startswith(("not_", "neg_")):
        raise ValueError("negative literals are outside the positive-Horn smoke")
    return value


@dataclass(frozen=True, order=True)
class Atom:
    predicate: str
    arguments: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "predicate", _identifier(self.predicate))
        object.__setattr__(
            self,
            "arguments",
            tuple(_identifier(item, variable=True) for item in self.arguments),
        )
        if not 0 < len(self.arguments) <= 3:
            raise ValueError("the smoke supports predicates of arity 1--3")

    @property
    def variables(self) -> frozenset[str]:
        return frozenset(item for item in self.arguments if item.startswith("?"))

    @property
    def ground(self) -> bool:
        return not self.variables

    def substitute(self, bindings: Mapping[str, str]) -> "Atom":
        return Atom(
            self.predicate,
            tuple(bindings.get(item, item) for item in self.arguments),
        )

    def as_dict(self) -> dict[str, Any]:
        return {"predicate": self.predicate, "arguments": list(self.arguments)}

    def __str__(self) -> str:
        return f"{self.predicate}({','.join(self.arguments)})"


_ATOM_TEXT = re.compile(r"^\s*([\w-]+)\s*\((.*?)\)\s*$", re.UNICODE)


def parse_atom(raw: Any) -> Atom:
    if isinstance(raw, Atom):
        return raw
    if isinstance(raw, str):
        match = _ATOM_TEXT.match(raw)
        if not match:
            raise ValueError(f"invalid atom string: {raw!r}")
        args = [item.strip() for item in match.group(2).split(",") if item.strip()]
        return Atom(match.group(1), tuple(args))
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return Atom(str(raw[0]), tuple(raw[1]))
    if not isinstance(raw, Mapping):
        raise ValueError("atom must be an object or p(a,b) string")
    extra = set(raw) - {"predicate", "arguments", "args"}
    if extra or "predicate" not in raw:
        raise ValueError(f"invalid atom fields: {sorted(extra)}")
    arguments = raw.get("arguments", raw.get("args"))
    if not isinstance(arguments, Sequence) or isinstance(arguments, (str, bytes)):
        raise ValueError("atom arguments must be a list")
    return Atom(str(raw["predicate"]), tuple(str(item) for item in arguments))


@dataclass(frozen=True)
class Rule:
    rule_id: str
    head: Atom
    body: tuple[Atom, ...]
    source_id: str

    def __post_init__(self) -> None:
        if not self.body:
            raise ValueError("a Horn rule needs at least one premise")
        if self.head.variables - frozenset().union(*(atom.variables for atom in self.body)):
            raise ValueError("unsafe Horn rule: every head variable must occur in the body")
        object.__setattr__(self, "body", tuple(sorted(set(self.body))))
        if not self.rule_id:
            object.__setattr__(self, "rule_id", sha256_text(self.signature)[:16])

    @property
    def signature(self) -> str:
        body = "&".join(str(atom) for atom in self.body)
        return f"{body}->{self.head}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "source_id": self.source_id,
            "head": self.head.as_dict(),
            "body": [atom.as_dict() for atom in self.body],
        }


@dataclass(frozen=True)
class Fragment:
    source_id: str
    source_text_sha256: str
    facts: tuple[Atom, ...] = ()
    rules: tuple[Rule, ...] = ()
    validated: bool = False
    validation_note: str = ""

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("fragment needs source_id")
        facts = tuple(sorted(set(self.facts)))
        if any(not atom.ground for atom in facts):
            raise ValueError("facts must be ground")
        rules = tuple(sorted(self.rules, key=lambda item: (item.signature, item.rule_id)))
        if any(rule.source_id != self.source_id for rule in rules):
            raise ValueError("rule source_id differs from fragment source_id")
        object.__setattr__(self, "facts", facts)
        object.__setattr__(self, "rules", rules)

    @property
    def empty(self) -> bool:
        return not self.facts and not self.rules

    @property
    def semantic_signature(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (
            tuple(str(atom) for atom in self.facts),
            tuple(rule.signature for rule in self.rules),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_text_sha256": self.source_text_sha256,
            "validated": self.validated,
            "validation_note": self.validation_note,
            "facts": [atom.as_dict() for atom in self.facts],
            "rules": [rule.as_dict() for rule in self.rules],
        }


def fragment_from_formal(
    raw: Any,
    *,
    source_id: str,
    source_text: str,
    validated: bool = True,
    validation_note: str = "oracle_after_execution",
) -> Fragment:
    """Normalize all formal-outcome spellings used by the smoke builders."""
    if raw is None:
        raw = {}
    if isinstance(raw, Mapping) and raw.get("formal_injection") is not None:
        raw = raw["formal_injection"]
    if not isinstance(raw, Mapping):
        raise ValueError("formal outcome must be an object")

    facts: list[Atom] = []
    rules: list[Rule] = []
    if raw.get("kind") in {"fact", "rule"}:
        if raw["kind"] == "fact":
            facts.append(parse_atom(raw["head"]))
        else:
            rules.append(
                Rule(
                    str(raw.get("rule_id") or ""),
                    parse_atom(raw["head"]),
                    tuple(parse_atom(item) for item in raw.get("body", [])),
                    source_id,
                )
            )
    else:
        for item in raw.get("facts", []) or []:
            facts.append(parse_atom(item))
        for index, item in enumerate(raw.get("rules", []) or []):
            if not isinstance(item, Mapping):
                raise ValueError("rule must be an object")
            rules.append(
                Rule(
                    str(item.get("rule_id") or item.get("id") or f"{source_id}:r{index}"),
                    parse_atom(item["head"]),
                    tuple(parse_atom(atom) for atom in item.get("body", [])),
                    source_id,
                )
            )
    return Fragment(
        source_id=source_id,
        source_text_sha256=sha256_text(source_text),
        facts=tuple(facts),
        rules=tuple(rules),
        validated=validated,
        validation_note=validation_note,
    )


@dataclass(frozen=True)
class ExecutionReceipt:
    source_id: str
    source_text_sha256: str
    sequence: int
    executed: bool = True


@dataclass(frozen=True)
class CommittedKB:
    fragments: tuple[Fragment, ...] = ()

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(fragment.source_id for fragment in self.fragments)

    def commit(self, receipt: ExecutionReceipt, fragment: Fragment) -> "CommittedKB":
        if not receipt.executed:
            raise ValueError("only an executed source may commit")
        if not fragment.validated:
            raise ValueError("fail-closed: unvalidated fragment cannot commit")
        if receipt.source_id != fragment.source_id:
            raise ValueError("receipt/fragment source mismatch")
        if receipt.source_text_sha256 != fragment.source_text_sha256:
            raise ValueError("receipt/fragment text hash mismatch")
        if fragment.source_id in self.source_ids:
            raise ValueError(f"source already committed: {fragment.source_id}")
        return CommittedKB(self.fragments + (fragment,))

    @property
    def facts(self) -> tuple[tuple[Atom, str], ...]:
        return tuple(
            (fact, fragment.source_id)
            for fragment in self.fragments
            for fact in fragment.facts
        )

    @property
    def rules(self) -> tuple[Rule, ...]:
        return tuple(rule for fragment in self.fragments for rule in fragment.rules)


@dataclass(frozen=True)
class ProofStep:
    atom: Atom
    kind: str
    source_id: str
    rule_id: str | None
    premises: tuple[Atom, ...]
    depth: int
    source_ids: frozenset[str]

    @property
    def rank(self) -> tuple[Any, ...]:
        return (
            len(self.source_ids),
            self.depth,
            tuple(sorted(self.source_ids)),
            self.rule_id or "",
            tuple(str(atom) for atom in self.premises),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "atom": self.atom.as_dict(),
            "kind": self.kind,
            "source_id": self.source_id,
            "rule_id": self.rule_id,
            "premises": [atom.as_dict() for atom in self.premises],
            "depth": self.depth,
            "source_ids": sorted(self.source_ids),
        }


@dataclass(frozen=True)
class Proof:
    query: Atom
    steps: tuple[ProofStep, ...]
    source_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query.as_dict(),
            "source_ids": list(self.source_ids),
            "steps": [step.as_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class LFPResult:
    closure: frozenset[Atom]
    provenance: Mapping[Atom, ProofStep]
    iterations: int
    delta_by_iteration: tuple[tuple[Atom, ...], ...]

    def entails(self, query: Atom) -> bool:
        return query in self.closure

    def proof(self, query: Atom) -> Proof | None:
        if query not in self.closure:
            return None
        ordered: list[ProofStep] = []
        visited: set[Atom] = set()

        def visit(atom: Atom) -> None:
            if atom in visited:
                return
            step = self.provenance[atom]
            for premise in step.premises:
                visit(premise)
            visited.add(atom)
            ordered.append(step)

        visit(query)
        endpoint = self.provenance[query]
        return Proof(query, tuple(ordered), tuple(sorted(endpoint.source_ids)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "closure": [atom.as_dict() for atom in sorted(self.closure)],
            "iterations": self.iterations,
            "delta_by_iteration": [
                [atom.as_dict() for atom in delta] for delta in self.delta_by_iteration
            ],
        }


def _match(pattern: Atom, ground: Atom, bindings: Mapping[str, str]) -> dict[str, str] | None:
    if pattern.predicate != ground.predicate or len(pattern.arguments) != len(ground.arguments):
        return None
    result = dict(bindings)
    for wanted, observed in zip(pattern.arguments, ground.arguments):
        if wanted.startswith("?"):
            old = result.get(wanted)
            if old is not None and old != observed:
                return None
            result[wanted] = observed
        elif wanted != observed:
            return None
    return result


def _rule_matches(rule: Rule, closure: Iterable[Atom]) -> Iterable[tuple[Atom, tuple[Atom, ...]]]:
    by_predicate: dict[tuple[str, int], list[Atom]] = {}
    for atom in closure:
        by_predicate.setdefault((atom.predicate, len(atom.arguments)), []).append(atom)
    states: list[tuple[dict[str, str], tuple[Atom, ...]]] = [({}, ())]
    for premise in rule.body:
        next_states: list[tuple[dict[str, str], tuple[Atom, ...]]] = []
        candidates = sorted(by_predicate.get((premise.predicate, len(premise.arguments)), []))
        for bindings, matched in states:
            for candidate in candidates:
                updated = _match(premise, candidate, bindings)
                if updated is not None:
                    next_states.append((updated, matched + (candidate,)))
        states = next_states
        if not states:
            break
    for bindings, premises in states:
        head = rule.head.substitute(bindings)
        if not head.ground:
            raise AssertionError("safe rule produced a non-ground head")
        yield head, premises


def least_fixed_point(kb: CommittedKB) -> LFPResult:
    closure: set[Atom] = set()
    provenance: dict[Atom, ProofStep] = {}
    for fact, source_id in sorted(kb.facts, key=lambda item: (item[0], item[1])):
        candidate = ProofStep(fact, "fact", source_id, None, (), 0, frozenset({source_id}))
        old = provenance.get(fact)
        closure.add(fact)
        if old is None or candidate.rank < old.rank:
            provenance[fact] = candidate

    deltas: list[tuple[Atom, ...]] = [tuple(sorted(closure))] if closure else []
    iterations = 0
    while True:
        iterations += 1
        new_atoms: set[Atom] = set()
        changed_proof = False
        snapshot = frozenset(closure)
        for rule in sorted(kb.rules, key=lambda item: (item.signature, item.rule_id, item.source_id)):
            for head, premises in _rule_matches(rule, snapshot):
                premise_steps = [provenance[premise] for premise in premises]
                source_ids = frozenset({rule.source_id}).union(
                    *(step.source_ids for step in premise_steps)
                )
                candidate = ProofStep(
                    head,
                    "rule",
                    rule.source_id,
                    rule.rule_id,
                    premises,
                    1 + max((step.depth for step in premise_steps), default=0),
                    source_ids,
                )
                old = provenance.get(head)
                if head not in closure:
                    new_atoms.add(head)
                if old is None or candidate.rank < old.rank:
                    provenance[head] = candidate
                    changed_proof = True
        if new_atoms:
            closure.update(new_atoms)
            deltas.append(tuple(sorted(new_atoms)))
        if not new_atoms and not changed_proof:
            break
        if iterations > 10_000:
            raise RuntimeError("LFP did not converge")
    return LFPResult(frozenset(closure), provenance, iterations - 1, tuple(deltas))


def verify_proof(kb: CommittedKB, proof: Proof | None) -> bool:
    if proof is None:
        return False
    facts = {(atom, source_id) for atom, source_id in kb.facts}
    rules = {(rule.rule_id, rule.source_id): rule for rule in kb.rules}
    established: set[Atom] = set()
    used_sources: set[str] = set()
    for step in proof.steps:
        if step.kind == "fact":
            if (step.atom, step.source_id) not in facts or step.premises:
                return False
        elif step.kind == "rule":
            rule = rules.get((step.rule_id or "", step.source_id))
            if rule is None or any(premise not in established for premise in step.premises):
                return False
            valid = any(
                head == step.atom and premises == step.premises
                for head, premises in _rule_matches(rule, established)
            )
            if not valid:
                return False
        else:
            return False
        established.add(step.atom)
        used_sources.add(step.source_id)
    return (
        proof.query in established
        and tuple(sorted(used_sources)) == proof.source_ids
        and set(proof.source_ids) <= set(kb.source_ids)
    )


def source_set_sufficient(kb: CommittedKB, query: Atom, source_ids: Iterable[str]) -> bool:
    wanted = frozenset(source_ids)
    subset = CommittedKB(tuple(fragment for fragment in kb.fragments if fragment.source_id in wanted))
    return least_fixed_point(subset).entails(query)

