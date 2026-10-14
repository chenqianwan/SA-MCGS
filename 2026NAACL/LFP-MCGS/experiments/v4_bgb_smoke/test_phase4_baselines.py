#!/usr/bin/env python3
"""Offline invariants for the Phase-4 SA-MCGS-lineage baselines."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from lfp_core import Atom, Fragment, Rule
from run_phase4_baselines import (
    ROOT,
    _merge_source_fragments,
    _raw_public_cases,
    deduplicate_window_sets,
    deterministic_windows,
    parse_args,
)
from run_phase2 import PublicSource


class Phase4BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = _raw_public_cases(ROOT / "data" / "cases.jsonl", ROOT / "data" / "public_cases.jsonl")

    def test_every_center_gets_a_deterministic_window(self) -> None:
        for raw in self.rows.values():
            windows = deterministic_windows(raw, 4)
            self.assertEqual(len(windows), len(raw["source_order"]))
            self.assertEqual([window[0] for window in windows], raw["source_order"])
            self.assertTrue(all(len(window) == min(4, raw["carrier_size"]) for window in windows))

    def test_windows_use_only_public_topology_nodes(self) -> None:
        for raw in self.rows.values():
            allowed = set(raw["source_order"])
            for window in deterministic_windows(raw, 4):
                self.assertLessEqual(set(window), allowed)
                self.assertEqual(len(window), len(set(window)))

    def test_unordered_duplicate_windows_are_reused(self) -> None:
        windows = [("a", "b", "c"), ("b", "a", "c"), ("a", "c", "d")]
        self.assertEqual(
            deduplicate_window_sets(windows),
            [("a", "b", "c"), ("a", "c", "d")],
        )

    def test_phase4_cli_is_xhub_only_by_default(self) -> None:
        with patch.object(sys, "argv", ["run_phase4_baselines.py"]):
            args = parse_args()
        self.assertEqual(args.provider, "xhub")
        self.assertEqual(args.model, "qwen-turbo")
        self.assertFalse(hasattr(args, "ollama_url"))

    def test_fragment_union_is_order_invariant(self) -> None:
        source = PublicSource("s", "seed(x) and q(?x) <- seed(?x)", "h")
        fact = Fragment("s", "ignored", (Atom("seed", ("x",)),), (), True, "t")
        rule = Rule("r", Atom("q", ("?x",)), (Atom("seed", ("?x",)),), "s")
        relation = Fragment("s", "ignored", (), (rule,), True, "t")
        left = _merge_source_fragments(source, [fact, relation])
        right = _merge_source_fragments(source, [relation, fact])
        self.assertEqual(left.semantic_signature, right.semantic_signature)

    def test_model_visible_rows_have_no_gold_fields(self) -> None:
        forbidden = {"expected_label", "formal_by_source", "minimum_source_cover", "proof"}
        for raw in self.rows.values():
            self.assertFalse(forbidden & set(raw))


if __name__ == "__main__":
    unittest.main()
