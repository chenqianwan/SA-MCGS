#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lfp_core import (  # noqa: E402
    Atom,
    CommittedKB,
    ExecutionReceipt,
    Fragment,
    Rule,
    least_fixed_point,
    sha256_text,
    source_set_sufficient,
    verify_proof,
)
from local_parser import extract_controlled_note, validate_model_output  # noqa: E402


class LFPTests(unittest.TestCase):
    def fragment(self, source_id: str, text: str, facts=(), rules=()) -> Fragment:
        return Fragment(source_id, sha256_text(text), tuple(facts), tuple(rules), True, "test")

    def commit(self, kb: CommittedKB, fragment: Fragment, text: str, index: int) -> CommittedKB:
        return kb.commit(
            ExecutionReceipt(fragment.source_id, sha256_text(text), index),
            fragment,
        )

    def test_cycle_without_seed_does_not_self_prove(self) -> None:
        a, b = Atom("a", ("case",)), Atom("b", ("case",))
        f1 = self.fragment("s1", "one", rules=(Rule("r1", b, (a,), "s1"),))
        f2 = self.fragment("s2", "two", rules=(Rule("r2", a, (b,), "s2"),))
        kb = self.commit(CommittedKB(), f1, "one", 1)
        kb = self.commit(kb, f2, "two", 2)
        result = least_fixed_point(kb)
        self.assertFalse(result.entails(a))
        self.assertFalse(result.entails(b))

    def test_seed_chain_has_source_linked_proof(self) -> None:
        a, b, q = Atom("a", ("case",)), Atom("b", ("case",)), Atom("q", ("case",))
        fragments = (
            self.fragment("seed", "one", facts=(a,)),
            self.fragment("bridge", "two", rules=(Rule("r1", b, (a,), "bridge"),)),
            self.fragment("witness", "three", rules=(Rule("r2", q, (b,), "witness"),)),
        )
        kb = CommittedKB()
        for index, (fragment, text) in enumerate(zip(fragments, ("one", "two", "three")), 1):
            kb = self.commit(kb, fragment, text, index)
        result = least_fixed_point(kb)
        proof = result.proof(q)
        self.assertTrue(result.entails(q))
        self.assertTrue(verify_proof(kb, proof))
        self.assertEqual(proof.source_ids, ("bridge", "seed", "witness"))
        self.assertTrue(source_set_sufficient(kb, q, proof.source_ids))
        self.assertFalse(source_set_sufficient(kb, q, ("seed", "witness")))

    def test_commit_requires_execution_validation_and_matching_hash(self) -> None:
        fragment = self.fragment("s1", "text", facts=(Atom("a", ("x",)),))
        with self.assertRaises(ValueError):
            CommittedKB().commit(ExecutionReceipt("s1", sha256_text("text"), 1, False), fragment)
        with self.assertRaises(ValueError):
            CommittedKB().commit(ExecutionReceipt("s1", sha256_text("other"), 1), fragment)
        invalid = Fragment("s1", sha256_text("text"), fragment.facts, (), False, "")
        with self.assertRaises(ValueError):
            CommittedKB().commit(ExecutionReceipt("s1", sha256_text("text"), 1), invalid)


class ParserTests(unittest.TestCase):
    def test_only_explicit_controlled_marker_is_visible(self) -> None:
        text = "Unrelated German law.\n[CONTROLLED-LFP-NOTE]\nseed_ready(case_1)\n[/CONTROLLED-LFP-NOTE]"
        self.assertEqual(extract_controlled_note(text), "seed_ready(case_1)")
        self.assertIsNone(extract_controlled_note("Unrelated German law only."))

    def test_strict_model_output_is_source_anchored(self) -> None:
        note = "Symbolisch: bridge_ready(case_1) <- seed_ready(case_1)."
        rendered = f"German original\n[CONTROLLED-LFP-NOTE]\n{note}\n[/CONTROLLED-LFP-NOTE]"
        raw = {
            "decision": "commit",
            "facts": [],
            "rules": [{
                "head": {"predicate": "bridge_ready", "arguments": ["case_1"]},
                "body": [{"predicate": "seed_ready", "arguments": ["case_1"]}],
                "evidence": "bridge_ready(case_1) <- seed_ready(case_1).",
            }],
        }
        decision, fragment = validate_model_output(
            raw, source_id="s1", rendered_text=rendered, note=note
        )
        self.assertEqual(decision, "commit")
        self.assertEqual(len(fragment.rules), 1)

        hallucinated = {
            "decision": "commit",
            "facts": [{"predicate": "query", "arguments": ["case_1"], "evidence": note}],
            "rules": [],
        }
        with self.assertRaises(ValueError):
            validate_model_output(
                hallucinated, source_id="s1", rendered_text=rendered, note=note
            )


if __name__ == "__main__":
    unittest.main()

