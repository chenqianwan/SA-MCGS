#!/usr/bin/env python3
"""Integrity tests for the controlled BGB smoke corpus."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx


HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
SPEC = importlib.util.spec_from_file_location("bgb_case_builder", HERE / "build_cases.py")
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class BGBCaseBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run([sys.executable, str(HERE / "build_cases.py")], check=True, capture_output=True, text=True)
        cls.public = read_jsonl(DATA / "public_cases.jsonl")
        cls.gold = read_jsonl(DATA / "gold_sidecar.jsonl")
        cls.combined = read_jsonl(DATA / "cases.jsonl")
        cls.manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))

    def test_inventory_counts_and_tiers(self) -> None:
        self.assertEqual(len(self.public), 30)
        self.assertEqual(len(self.gold), 30)
        self.assertEqual(len(self.combined), 30)
        self.assertEqual(Counter(case["carrier_size"] for case in self.public), {3: 5, 5: 5, 7: 5, 9: 5, 11: 5, 25: 5})
        self.assertEqual(Counter(case["carrier_tier"] for case in self.public), {"smoke": 20, "pressure-only": 10})
        self.assertEqual(self.manifest["native_scc_inventory"], {"2": 8, "3": 4, "4": 4, "5": 1, "7": 1, "9": 1, "11": 1, "25": 1})

    def test_public_and_gold_are_separate_and_aligned(self) -> None:
        self.assertEqual([case["case_id"] for case in self.public], [case["case_id"] for case in self.gold])
        for public, gold, combined in zip(self.public, self.gold, self.combined, strict=True):
            encoded_public = builder.canonical_json(public)
            self.assertNotIn('"expected_label"', encoded_public)
            self.assertNotIn('"formal_program"', encoded_public)
            self.assertNotIn('"oracle"', encoded_public)
            self.assertEqual(combined["public_case"], public)
            self.assertEqual(combined["evaluator_sidecar"], gold)

    def test_append_only_patches_and_frozen_original_windows(self) -> None:
        public_by_id = {case["case_id"]: case for case in self.public}
        for gold in self.gold:
            public = public_by_id[gold["case_id"]]
            sources = {source["source_id"]: source for source in public["sources"]}
            for source in sources.values():
                self.assertEqual(builder.sha256_text(source["original_text"]), source["original_text_sha256"])
                self.assertEqual(builder.sha256_text(source["rendered_text"]), source["rendered_text_sha256"])
            for patch in gold["injected_patches"]:
                source = sources[patch["source_id"]]
                self.assertEqual(patch["original_text_sha256"], source["original_text_sha256"])
                if patch["operation"] == "append":
                    self.assertEqual(source["rendered_text"], source["original_text"] + "\n\n" + patch["appended_note"])
                    self.assertTrue(patch["appended_note"].startswith("[CONTROLLED-LFP-NOTE]\n"))
                    self.assertTrue(patch["appended_note"].endswith("\n[/CONTROLLED-LFP-NOTE]"))
                else:
                    self.assertEqual(patch["operation"], "omit_noop")
                    self.assertEqual(source["rendered_text"], source["original_text"])
                    self.assertEqual(patch["formal_injection"], {"facts": [], "rules": []})

    def test_oracles_reexecute_and_all_gates_pass(self) -> None:
        for gold in self.gold:
            fragments = []
            for raw in gold["formal_program"]["fragments"]:
                rules = tuple(
                    (rule["head"], tuple(rule["body"]), rule["rule_id"])
                    for rule in raw["rules"]
                )
                fragments.append(
                    builder.Fragment(
                        raw["source_id"],
                        raw["fragment_id"],
                        tuple(raw["facts"]),
                        rules,
                    )
                )
            closure_a, _ = builder.closure_naive(fragments)
            closure_b = builder.closure_agenda(fragments)
            self.assertEqual(closure_a, closure_b)
            expected_entailed = gold["expected_label"] == builder.LABEL_ENTAILED
            self.assertEqual(gold["query_atom"] in closure_a, expected_entailed)
            self.assertTrue(gold["oracle"]["all_gates_pass"])
            if expected_entailed:
                self.assertEqual(set(gold["oracle"]["minimum_source_cover"]), set(gold["required_injected_source_ids"]))
                self.assertEqual(set(gold["oracle"]["proof_source_ids"]), set(gold["required_injected_source_ids"]))

    def test_pdbc_share_topology_and_dag_is_separate(self) -> None:
        grouped = defaultdict(dict)
        for case in self.public:
            grouped[case["carrier_id"]][case["condition"]] = case
        for conditions in grouped.values():
            native = [conditions[name] for name in ("Productive", "Decoy", "Broken", "Clean")]
            self.assertEqual(len({case["topology"]["sha256"] for case in native}), 1)
            self.assertEqual(len({case["original_window_set_sha256"] for case in native}), 1)
            dag = conditions["Matched-DAG"]["topology"]
            self.assertNotEqual(dag["sha256"], native[0]["topology"]["sha256"])
            control = nx.DiGraph()
            control.add_nodes_from(dag["nodes"])
            control.add_edges_from((edge["source"], edge["target"]) for edge in dag["edges"])
            self.assertTrue(nx.is_directed_acyclic_graph(control))
            self.assertGreater(len(dag["edge_delta"]["removed"]), 0)

    def test_frozen_root_can_acquire_every_required_source(self) -> None:
        public_by_id = {case["case_id"]: case for case in self.public}
        for gold in self.gold:
            public = public_by_id[gold["case_id"]]
            navigation = gold["navigation_contract"]
            topology = public["topology"]
            graph = nx.DiGraph()
            graph.add_nodes_from(topology["nodes"])
            graph.add_edges_from((edge["source"], edge["target"]) for edge in topology["edges"])
            root = navigation["root_source_id"]
            reachable = nx.descendants(graph, root) | {root}
            self.assertEqual(public["root_source_id"], root)
            self.assertEqual(reachable, set(topology["nodes"]))
            self.assertTrue(set(navigation["required_proof_source_ids"]).issubset(reachable))
            self.assertTrue(set(navigation["navigation_target_source_ids"]).issubset(reachable))
            route = navigation["reference_route"]
            self.assertEqual(route[0], root)
            self.assertTrue(all(graph.has_edge(source, target) for source, target in zip(route, route[1:])))
            self.assertTrue(set(navigation["navigation_target_source_ids"]).issubset(route))
            self.assertEqual(navigation["reference_route_move_cost"], len(route) - 1)
            self.assertEqual(
                navigation["reference_route_total_action_cost"],
                navigation["reference_route_move_cost"] + navigation["reference_route_read_cost"],
            )
            self.assertLessEqual(
                navigation["reference_route_total_action_cost"],
                navigation["default_action_budget"],
            )
            self.assertEqual(navigation["reachable_exact_lfp_label"], gold["expected_label"])
            self.assertTrue(gold["oracle"]["gates"]["reachable_exact_lfp_label_matches_expected"])

    def test_manifest_artifact_hashes(self) -> None:
        self.assertEqual(self.manifest["status"], "PASS")
        self.assertTrue(all(self.manifest["global_gates"].values()))
        for name, record in self.manifest["outputs"].items():
            path = DATA / name
            self.assertEqual(builder.sha256_file(path), record["sha256"])
            self.assertEqual(path.stat().st_size, record["byte_count"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
