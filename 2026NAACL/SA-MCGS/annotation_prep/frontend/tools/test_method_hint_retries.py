#!/usr/bin/env python3
"""Read-only source regression tests; history-write checks use temporary files only."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_method_hints as hints


class FrozenRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.codebook = hints.load_json(hints.DEFAULT_CODEBOOK)
        cls.originals = hints.pre_results("sa-mcgs", hints.DEFAULT_GPT_PRE_SA, hints.DEFAULT_GEMINI_PRE_SA)
        cls.read_json = staticmethod(hints.load_json)

    def test_frozen_retries_recover_21_without_mutating_originals(self) -> None:
        digest = hints.canonical_hash(list(self.originals.values()))
        merged, update = hints.merge_frozen_sa_retries(self.originals, self.codebook)
        self.assertEqual(digest, hints.canonical_hash(list(self.originals.values())))
        self.assertEqual((update["retry_cells"], update["recovered_cells"], update["remaining_sa_invalid_cells"]), (24, 21, 3))
        self.assertEqual(sum(not row.get("cost_audit_error") for row in merged.values()), 33)
        for key, original in self.originals.items():
            if not original.get("cost_audit_error"):
                self.assertIs(merged[key], original)
                self.assertNotIn("_hint_source_attempt", merged[key])
        for model in hints.MODELS:
            self.assertIsNone(merged[("pre_cuad_24_92ef35e902e6", model)]["cost_audit_error"])
        unresolved = {key[0] for key, row in merged.items() if row.get("cost_audit_error")}
        self.assertEqual(unresolved, {"pre_cuad_16_4df2ab10e4b2", "pre_cuad_25_e97c2968e072", "pre_cuad_34_0e1882106beb"})

    def assert_reject_mutated_retry(self, mutate) -> None:
        target = hints.RETRY_ROOT / "sa_retry_gpt10" / "results" / "pre_cuad_24_92ef35e902e6__gpt-4o__sa-mcgs__sa-mcgs.json"

        def read(path):
            result = self.read_json(path)
            if path == target:
                result = copy.deepcopy(result)
                mutate(result)
            return result

        with mock.patch.object(hints, "load_json", side_effect=read):
            with self.assertRaises(hints.HintBuildError):
                hints.merge_frozen_sa_retries(self.originals, self.codebook)

    def test_rejects_unexpected_model(self) -> None:
        self.assert_reject_mutated_retry(lambda value: value.update(model="other-model"))

    def test_rejects_node_mismatch(self) -> None:
        self.assert_reject_mutated_retry(lambda value: value["scc_clause_ids"].pop())

    def test_rejects_source_fingerprint_change(self) -> None:
        self.assert_reject_mutated_retry(lambda value: value.update(pre_content_fingerprint="sha256:" + "0" * 64))

    def test_rejects_config_change_even_with_stale_fingerprint(self) -> None:
        self.assert_reject_mutated_retry(lambda value: value["sa_protocol"]["resolved_mcgs_config"]["alphago_mcgs"].update(budget=61))

    def test_rejects_nested_identity_change(self) -> None:
        self.assert_reject_mutated_retry(lambda value: value["case_identity"].update(method="lea"))

    def test_rejects_new_terminal_failure_in_reported_success(self) -> None:
        self.assert_reject_mutated_retry(lambda value: value.update(terminal_json_failure_count=1))

    def test_rejects_transport_audit_change(self) -> None:
        self.assert_reject_mutated_retry(lambda value: value["llm_usage_summary"].update(failed_api_calls=1))

    def test_invalid_lea_reason_is_validation_not_network(self) -> None:
        path = hints.DEFAULT_GPT_PRE / "pre_cuad_34_0e1882106beb__gpt-4o__lea.json"
        value = hints.strict_invalid_hint(self.read_json(path))
        self.assertEqual(value["status"], "strict_invalid")
        self.assertIn("API 已成功返回", value["reason_zh"])
        self.assertIn("严格格式校验", value["reason_zh"])
        self.assertNotIn("selected", value)

    def test_updated_public_case_keeps_original_valid_cells(self) -> None:
        merged, _ = hints.merge_frozen_sa_retries(self.originals, self.codebook)
        lea = hints.pre_results("lea", hints.DEFAULT_GPT_PRE, hints.DEFAULT_GEMINI_PRE)
        for record in self.codebook["records"]:
            master = record["master_record"]
            if not master.get("unmodified"):
                continue
            before = hints.build_pre_case(record, lea, self.originals)
            after = hints.build_pre_case(record, lea, merged)
            for sid, section in before["sections"].items():
                self.assertEqual(section["methods"]["lea"], after["sections"][sid]["methods"]["lea"])
                for model in hints.MODELS:
                    old = section["methods"]["sa-mcgs"]["models"][model]
                    new = after["sections"][sid]["methods"]["sa-mcgs"]["models"][model]
                    if old["status"] == "available":
                        self.assertEqual(old, new)
                    else:
                        self.assertEqual(new["source_attempt"], "retry_20260909")
                        self.assertEqual(new["original_status"], "strict_invalid")


class HintHistoryTests(unittest.TestCase):
    def test_history_preserved_and_noop_does_not_change_hash(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hint-pack-test-") as directory:
            path = Path(directory) / "method_hints.json"
            baseline = {"source_manifest_hash": "frozen-test-manifest", "cases": {"P1": {"status": "strict_invalid"}}}
            first, changed = hints.save_hint_pack(baseline, path)
            self.assertTrue(changed)
            first_bytes = path.read_bytes()
            first_mtime = path.stat().st_mtime_ns
            same, changed = hints.save_hint_pack(copy.deepcopy(baseline), path)
            self.assertFalse(changed)
            self.assertEqual(same, first)
            self.assertEqual(path.read_bytes(), first_bytes)
            self.assertEqual(path.stat().st_mtime_ns, first_mtime)
            updated = copy.deepcopy(baseline)
            updated["cases"]["P1"]["status"] = "available"
            second, changed = hints.save_hint_pack(updated, path)
            self.assertTrue(changed)
            self.assertEqual(second["previous_hint_pack_hashes"], [first["hint_pack_hash"]])
            archive = path.parent / "history" / f"method_hints.{first['hint_pack_hash'].split(':')[1]}.json"
            self.assertEqual(archive.read_bytes(), first_bytes)
            second_bytes = path.read_bytes()
            again, changed = hints.save_hint_pack(updated, path)
            self.assertFalse(changed)
            self.assertEqual(again, second)
            self.assertEqual(path.read_bytes(), second_bytes)
            self.assertNotIn(second["hint_pack_hash"], second["previous_hint_pack_hashes"])

    def test_rejects_corrupt_previous_pack(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hint-pack-test-") as directory:
            path = Path(directory) / "method_hints.json"
            first, _ = hints.save_hint_pack({"source_manifest_hash": "frozen", "cases": {}}, path)
            first["cases"] = {"corrupt": True}
            path.write_text(json.dumps(first), encoding="utf-8")
            with self.assertRaises(hints.HintBuildError):
                hints.save_hint_pack({"source_manifest_hash": "frozen", "cases": {}}, path)


if __name__ == "__main__":
    unittest.main()
