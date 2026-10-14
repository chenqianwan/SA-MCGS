#!/usr/bin/env python3
"""Regression tests; every label-bearing fixture is explicitly synthetic."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import annotation_analysis as aa


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
ANNOTATION_PREP = HERE.parent
SYN_MANIFEST = FIXTURES / "synthetic_manifest.json"
SYN_CODEBOOK = FIXTURES / "synthetic_codebook.json"
SYN_MASTER = FIXTURES / "synthetic_master.json"
SYN_POST_CATALOG = FIXTURES / "synthetic_post_identity_catalog.json"
SYN_TRANSLATIONS = FIXTURES / "synthetic_translations.json"
SYN_LEGACY = FIXTURES / "synthetic_legacy_labels.json"
SYN_LEGACY_SOURCE = FIXTURES / "synthetic_legacy_source.json"
PROD_MANIFEST = ANNOTATION_PREP / "frontend" / "data" / "manifest.json"
PROD_CODEBOOK = ANNOTATION_PREP / "internal" / "private_codebook.json"
PROD_TRANSLATIONS = ANNOTATION_PREP / "frontend" / "data" / "translations_zh.json"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def write_temp(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class AnnotationAnalysisTests(unittest.TestCase):
    maxDiff = None

    def fixture_paths(self) -> list[Path]:
        return [FIXTURES / f"synthetic_expert_{index}.json" for index in (1, 2, 3)]

    def freeze_options(self) -> dict:
        return {
            "export_paths": self.fixture_paths(),
            "protocol_id": "synthetic-protocol-v1",
            "frozen_by": "SYN-FREEZER",
            "frozen_at": "2026-01-01T00:00:00Z",
            "confirm_outcome_blind_freeze": True,
            "score_models": ["synthetic-model"],
            "score_methods": ["synthetic-method"],
            "score_strata": list(aa.FORMAL_STRATUM_COUNTS),
        }

    def synthetic_layout(self) -> dict:
        return aa.load_layout(SYN_MANIFEST, SYN_CODEBOOK, SYN_TRANSLATIONS)

    def merge_synthetic(self, out: Path) -> dict[str, Path]:
        return aa.merge_to_dir(
            SYN_MANIFEST,
            SYN_CODEBOOK,
            SYN_TRANSLATIONS,
            self.fixture_paths(),
            out / "merge",
        )

    def bound_adjudication(self, merged: dict, out: Path) -> Path:
        adjudication = load_fixture("synthetic_adjudication_filled.json")
        adjudication["merged_artifact_sha256"] = merged["artifact_sha256"]
        adjudication = aa.seal(adjudication)
        path = out / "adjudication_filled.json"
        write_temp(path, adjudication)
        return path

    def freeze_synthetic(self, out: Path) -> tuple[dict, Path, dict[str, Path], Path]:
        paths = self.merge_synthetic(out)
        merged = aa.read_json(paths["merged"])
        adjudication_path = self.bound_adjudication(merged, out)
        frozen = aa.freeze_labels(
            paths["merged"],
            adjudication_path,
            SYN_MANIFEST,
            SYN_CODEBOOK,
            SYN_TRANSLATIONS,
            SYN_LEGACY,
            export_paths=self.fixture_paths(),
            protocol_id="synthetic-protocol-v1",
            frozen_by="SYN-FREEZER",
            frozen_at="2026-01-01T00:00:00Z",
            confirm_outcome_blind_freeze=True,
            score_models=["synthetic-model"],
            score_methods=["synthetic-method"],
            score_strata=list(aa.FORMAL_STRATUM_COUNTS),
        )
        frozen_path = out / "frozen.json"
        write_temp(frozen_path, frozen)
        return frozen, frozen_path, paths, adjudication_path

    @staticmethod
    def xlsx_tables() -> tuple[list[dict], list[dict], list[dict]]:
        source = load_fixture("synthetic_expert_1.json")
        case_rows = []
        section_rows = []
        for order_index, case_id in enumerate(source["order"], start=1):
            annotation = source["annotations"][case_id]
            case_rows.append({
                "专家编号": "专家 1",
                "匿名标注者编号": source["anonymous_reviewer_id"],
                "展示顺序": order_index,
                "样本编号": case_id,
                "目标冲突代码": annotation["target_conflict"],
                "材料充分性代码": annotation["evidence_sufficient"],
                "更多上下文代码": annotation["need_more_context"],
                "判断信心_1到5": annotation["confidence"],
                "完成状态": "已完成",
                "manifest_hash": source["manifest_hash"],
                "translation_pack_hash": source["translation_pack_hash"],
                "整体备注": annotation["comments"],
                "保存时间": annotation["saved_at"],
            })
            for section_id, section in annotation["sections"].items():
                section_rows.append({
                    "专家编号": "专家 1",
                    "匿名标注者编号": source["anonymous_reviewer_id"],
                    "样本编号": case_id,
                    "段落编号": section_id,
                    "段落作用代码": section["role"],
                    "是否最小证据": "是" if section["minimal_evidence"] else "否",
                    "是否修复材料": "是" if section["repair_packet"] else "否",
                    "段落备注": section["note"],
                })
        metadata = [{
            "研究编号": source["study_id"],
            "专家编号": "专家 1",
            "匿名标注者编号": source["anonymous_reviewer_id"],
            "manifest_hash": source["manifest_hash"],
            "translation_pack_hash": source["translation_pack_hash"],
            "导出时间": source["exported_at"],
        }]
        return case_rows, section_rows, metadata

    def test_current_production_layout_metadata_only(self):
        audit = aa.layout_audit(PROD_MANIFEST, PROD_CODEBOOK, PROD_TRANSLATIONS)
        self.assertEqual(audit["counts"], aa.FORMAL_STRATUM_COUNTS)
        self.assertEqual(audit["export_contract"]["json_schema"], aa.EXPORT_SCHEMA)
        self.assertEqual(
            audit["gates"]["formal_legacy12_freeze_gate"],
            "BLOCKED_UNTIL_EXPLICIT_VERIFIED_LEGACY_LABEL_ARTIFACT",
        )
        aa.verify_seal(audit)

    def test_full_synthetic_closure_and_zero_preserving_cleanliness(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            frozen, frozen_path, paths, _ = self.freeze_synthetic(out)
            merged = aa.read_json(paths["merged"])
            iaa = aa.read_json(paths["iaa"])
            template = aa.read_json(paths["adjudication"])
            aa.verify_seal(merged)
            aa.verify_seal(iaa)
            aa.verify_seal(template)
            aa.verify_seal(frozen, "label_bundle_sha256")
            self.assertEqual(merged["counts"], {"post_new24": 2, "pre18": 2})
            self.assertEqual(
                {row["case_id"] for row in template["cases"]},
                {"SYN-PRE-B", "SYN-POST-B"},
            )
            self.assertIn(
                "krippendorff_alpha_nominal",
                iaa["strata"]["pre18"]["target_conflict"],
            )
            self.assertEqual(
                frozen["counts"],
                {"post_legacy12": 2, "post_new24": 2, "pre18": 2},
            )
            self.assertEqual(frozen["source_identity"], merged["source_identity"])

            system = load_fixture("synthetic_system_outputs.template.json")
            system["label_bundle_sha256"] = frozen["label_bundle_sha256"]
            system_path = out / "system.json"
            write_temp(system_path, system)
            cleanliness, summary = aa.score_system_outputs(
                frozen_path,
                system_path,
                bootstrap_samples=200,
                seed=7,
                require_complete_grid=True,
                expected_models=["synthetic-model"],
                expected_methods=["synthetic-method"],
                expected_strata=list(aa.FORMAL_STRATUM_COUNTS),
            )
            aa.verify_seal(cleanliness)
            aa.verify_seal(summary)
            self.assertEqual(len(cleanliness["records"]), 6)
            self.assertEqual(
                {group["stratum"] for group in summary["groups"]},
                set(aa.FORMAL_STRATUM_COUNTS),
            )
            invalid = next(
                row for row in cleanliness["records"]
                if row["case_id"] == "syn-legacy-b-uid"
            )
            self.assertEqual(invalid["expert_evidence_recall"], 0.0)
            self.assertEqual(invalid["repair_packet_coverage"], 0.0)
            self.assertEqual(invalid["excess_node_rate"], 0.0)
            self.assertEqual(invalid["expert_evidence_density"], 0.0)
            self.assertEqual(invalid["endpoint_recall"], 0.0)
            self.assertEqual(invalid["endpoint_density"], 0.0)
            legacy_group = next(
                group for group in summary["groups"]
                if group["stratum"] == "post_legacy12"
            )
            self.assertEqual(
                legacy_group["metrics"]["repair_packet_coverage"]
                ["denominator_case_presentations"],
                2,
            )

    def test_manifest_body_hash_is_recomputed(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = load_fixture("synthetic_manifest.json")
            manifest["cases"][0]["sections"][0]["text"] = "TAMPERED AFTER HASH"
            path = Path(temporary) / "manifest.json"
            write_temp(path, manifest)
            with self.assertRaisesRegex(aa.ValidationError, "Manifest body hash mismatch"):
                aa.load_layout(path, SYN_CODEBOOK, SYN_TRANSLATIONS)

    def test_translation_pack_hash_and_source_binding_are_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            stale = load_fixture("synthetic_translations.json")
            stale["cases"]["SYN-PRE-A"]["sections"]["S001"]["text_zh"] += "篡改"
            stale_path = out / "stale_translation.json"
            write_temp(stale_path, stale)
            with self.assertRaisesRegex(aa.ValidationError, "Translation pack body hash mismatch"):
                aa.load_layout(SYN_MANIFEST, SYN_CODEBOOK, stale_path)

            forged = load_fixture("synthetic_translations.json")
            forged["cases"]["SYN-PRE-A"]["sections"]["S001"]["source_hash"] = (
                "sha256:" + "0" * 64
            )
            unsigned = copy.deepcopy(forged)
            unsigned.pop("translation_pack_hash")
            forged["translation_pack_hash"] = aa.canonical_sha256(unsigned)
            forged_path = out / "forged_translation.json"
            write_temp(forged_path, forged)
            with self.assertRaisesRegex(aa.ValidationError, "Translation source hash mismatch"):
                aa.load_layout(SYN_MANIFEST, SYN_CODEBOOK, forged_path)

    def test_expert_export_must_match_verified_translation_pack(self):
        layout = self.synthetic_layout()
        payload = load_fixture("synthetic_expert_1.json")
        payload["translation_pack_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(aa.ValidationError, "verified translation pack"):
            aa.validate_expert_export(payload, layout, Path("synthetic_bad.json"))

    def test_wrong_export_manifest_hash_is_rejected(self):
        layout = self.synthetic_layout()
        payload = load_fixture("synthetic_expert_1.json")
        payload["manifest_hash"] = "0" * 64
        with self.assertRaisesRegex(aa.ValidationError, "manifest_hash mismatch"):
            aa.validate_expert_export(payload, layout, Path("synthetic_bad.json"))

    def test_codebook_records_must_be_exact_source_master_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            codebook = load_fixture("synthetic_codebook.json")
            codebook["source_master"] = str((FIXTURES / "synthetic_master.json").resolve())
            codebook["records"][0]["master_record"]["domain"] = "tampered-domain"
            path = Path(temporary) / "codebook.json"
            write_temp(path, codebook)
            with self.assertRaisesRegex(aa.ValidationError, "wrapper/master binding"):
                aa.load_layout(SYN_MANIFEST, path, SYN_TRANSLATIONS)

    def test_freeze_rejects_codebook_identity_change_after_merge(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            paths = self.merge_synthetic(out)
            merged = aa.read_json(paths["merged"])
            adjudication_path = self.bound_adjudication(merged, out)
            codebook = load_fixture("synthetic_codebook.json")
            codebook["source_master"] = str((FIXTURES / "synthetic_master.json").resolve())
            codebook["records"][0]["section_map"][0]["original_node_id"] = "changed-node"
            codebook_path = out / "changed_codebook.json"
            write_temp(codebook_path, codebook)
            with self.assertRaisesRegex(aa.ValidationError, "bijectively cover canonical nodes"):
                aa.freeze_labels(
                    paths["merged"], adjudication_path, SYN_MANIFEST,
                    codebook_path, SYN_TRANSLATIONS, SYN_LEGACY,
                    export_paths=self.fixture_paths(),
                    protocol_id="synthetic", frozen_by="SYN-FREEZER",
                    frozen_at="2026-01-01T00:00:00Z",
                    confirm_outcome_blind_freeze=True,
                    score_models=["synthetic-model"],
                    score_methods=["synthetic-method"],
                    score_strata=list(aa.FORMAL_STRATUM_COUNTS),
                )

    def test_adjudication_case_set_must_be_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            paths = self.merge_synthetic(out)
            merged = aa.read_json(paths["merged"])
            adjudication = load_fixture("synthetic_adjudication_filled.json")
            adjudication["merged_artifact_sha256"] = merged["artifact_sha256"]
            extra = copy.deepcopy(adjudication["cases"][0])
            extra["case_id"] = "SYN-PRE-A"
            extra["required_reasons"] = []
            extra["allowed_section_ids"] = ["S001", "S002"]
            adjudication["cases"].append(extra)
            adjudication = aa.seal(adjudication)
            path = out / "extra_adjudication.json"
            write_temp(path, adjudication)
            with self.assertRaisesRegex(aa.ValidationError, "must exactly match"):
                aa.freeze_labels(
                    paths["merged"], path, SYN_MANIFEST, SYN_CODEBOOK,
                    SYN_TRANSLATIONS, SYN_LEGACY,
                    export_paths=self.fixture_paths(),
                    protocol_id="synthetic", frozen_by="SYN-FREEZER",
                    frozen_at="2026-01-01T00:00:00Z",
                    confirm_outcome_blind_freeze=True,
                    score_models=["synthetic-model"],
                    score_methods=["synthetic-method"],
                    score_strata=list(aa.FORMAL_STRATUM_COUNTS),
                )

    def test_adjudication_requires_outcome_blind_attestation(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            paths = self.merge_synthetic(out)
            merged = aa.read_json(paths["merged"])
            base = load_fixture("synthetic_adjudication_filled.json")
            base["merged_artifact_sha256"] = merged["artifact_sha256"]
            variants = [
                ("declared_policy", lambda row: row.__setitem__(
                    "system_outcomes_must_remain_unseen", False
                ), "must state"),
                ("signed_attestation", lambda row: row["outcome_blind_attestation"].__setitem__(
                    "system_outcomes_unseen", False
                ), "attestation"),
            ]
            for name, mutate, error in variants:
                with self.subTest(name=name):
                    payload = copy.deepcopy(base)
                    mutate(payload)
                    payload = aa.seal(payload)
                    path = out / f"{name}.json"
                    write_temp(path, payload)
                    with self.assertRaisesRegex(aa.ValidationError, error):
                        aa.freeze_labels(
                            paths["merged"], path, SYN_MANIFEST, SYN_CODEBOOK,
                            SYN_TRANSLATIONS, SYN_LEGACY,
                            export_paths=self.fixture_paths(),
                            protocol_id="synthetic", frozen_by="SYN-FREEZER",
                            frozen_at="2026-01-01T00:00:00Z",
                            confirm_outcome_blind_freeze=True,
                            score_models=["synthetic-model"],
                            score_methods=["synthetic-method"],
                            score_strata=list(aa.FORMAL_STRATUM_COUNTS),
                        )

    def test_legacy_case_must_bind_post_content_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            layout = self.synthetic_layout()
            payload = load_fixture("synthetic_legacy_labels.json")
            payload["source_artifact_path"] = str(SYN_LEGACY_SOURCE.resolve())
            payload["cases"][0]["post_content_fingerprint"] = payload["cases"][1][
                "post_content_fingerprint"
            ]
            path = Path(temporary) / "legacy.json"
            write_temp(path, payload)
            with self.assertRaisesRegex(aa.ValidationError, "post_content_fingerprint mismatch"):
                aa.load_legacy_labels(path, layout)

    def test_legacy_source_artifact_and_provenance_are_fail_closed(self):
        layout = self.synthetic_layout()
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            bad_hash = load_fixture("synthetic_legacy_labels.json")
            bad_hash["source_artifact_path"] = str(SYN_LEGACY_SOURCE.resolve())
            bad_hash["source_artifact_sha256"] = "sha256:" + "0" * 64
            bad_hash_path = out / "bad_hash.json"
            write_temp(bad_hash_path, bad_hash)
            with self.assertRaisesRegex(aa.ValidationError, "source artifact hash mismatch"):
                aa.load_legacy_labels(bad_hash_path, layout)

            no_provenance = load_fixture("synthetic_legacy_labels.json")
            no_provenance["source_artifact_path"] = str(SYN_LEGACY_SOURCE.resolve())
            no_provenance["cases"][0]["label_provenance"] = ""
            no_provenance_path = out / "no_provenance.json"
            write_temp(no_provenance_path, no_provenance)
            with self.assertRaisesRegex(aa.ValidationError, "label_provenance is required"):
                aa.load_legacy_labels(no_provenance_path, layout)

    def test_missing_formal_legacy_artifact_is_an_explicit_gate(self):
        layout = self.synthetic_layout()
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing_legacy12.json"
            with self.assertRaisesRegex(aa.ValidationError, "legacy12 label gate BLOCKED"):
                aa.load_legacy_labels(missing, layout)

    def test_positive_sufficient_final_label_requires_repair_packet(self):
        with self.assertRaisesRegex(aa.ValidationError, "needs a repair packet"):
            aa._validate_final_fields(
                "present", "yes", "no", ["S001"], [], {"S001"}, "synthetic"
            )

    def test_complete_grid_uses_frozen_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            frozen, frozen_path, _, _ = self.freeze_synthetic(out)
            system = load_fixture("synthetic_system_outputs.template.json")
            system["label_bundle_sha256"] = frozen["label_bundle_sha256"]
            system_path = out / "system.json"
            write_temp(system_path, system)
            _, summary = aa.score_system_outputs(
                frozen_path, system_path, bootstrap_samples=20, seed=1,
                require_complete_grid=True,
            )
            self.assertEqual(
                summary["complete_grid_contract"]["source"],
                "frozen_label_bundle.score_protocol",
            )
            with self.assertRaisesRegex(aa.ValidationError, "differ from frozen score protocol"):
                aa.score_system_outputs(
                    frozen_path, system_path, bootstrap_samples=20, seed=1,
                    require_complete_grid=True,
                    expected_models=["other-model"],
                    expected_methods=["synthetic-method"],
                    expected_strata=list(aa.FORMAL_STRATUM_COUNTS),
                )
            incomplete = copy.deepcopy(system)
            incomplete["records"].pop()
            incomplete_path = out / "incomplete_system.json"
            write_temp(incomplete_path, incomplete)
            with self.assertRaisesRegex(aa.ValidationError, "System grid incomplete"):
                aa.score_system_outputs(
                    frozen_path, incomplete_path, bootstrap_samples=20, seed=1,
                    require_complete_grid=False,
                )

    def test_system_source_scc_uid_and_stratum_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            frozen, frozen_path, _, _ = self.freeze_synthetic(out)
            base = load_fixture("synthetic_system_outputs.template.json")
            base["label_bundle_sha256"] = frozen["label_bundle_sha256"]
            for field, error in (
                ("source_scc_uid", "source_scc_uid is required"),
                ("stratum", "stratum is required"),
            ):
                with self.subTest(field=field):
                    payload = copy.deepcopy(base)
                    payload["records"][0].pop(field)
                    path = out / f"missing_{field}.json"
                    write_temp(path, payload)
                    with self.assertRaisesRegex(aa.ValidationError, error):
                        aa.score_system_outputs(
                            frozen_path, path, bootstrap_samples=20, seed=1,
                            require_complete_grid=False,
                        )

    def test_xlsx_table_adapter_matches_current_headers(self):
        case_rows, section_rows, metadata = self.xlsx_tables()
        adapted = aa.xlsx_tables_to_payload(case_rows, section_rows, metadata)
        adapted["synthetic_fixture"] = True
        validated = aa.validate_expert_export(
            adapted, self.synthetic_layout(), Path("synthetic.xlsx")
        )
        self.assertEqual(validated["expert_id"], "expert_1")
        self.assertEqual(
            validated["annotations"]["SYN-POST-A"]["target_conflict"], "present"
        )

    def test_xlsx_rejects_wrong_section_reviewer_and_orphan_rows(self):
        case_rows, section_rows, metadata = self.xlsx_tables()
        wrong_reviewer = copy.deepcopy(section_rows)
        wrong_reviewer[0]["匿名标注者编号"] = "SYN-OTHER-REVIEWER"
        with self.assertRaisesRegex(aa.ValidationError, "Reviewer ID differs.*section"):
            aa.xlsx_tables_to_payload(case_rows, wrong_reviewer, metadata)

        orphan = copy.deepcopy(section_rows)
        orphan_row = copy.deepcopy(orphan[0])
        orphan_row["样本编号"] = "SYN-ORPHAN"
        orphan_row["段落编号"] = "S999"
        orphan.append(orphan_row)
        with self.assertRaisesRegex(aa.ValidationError, "orphan cases"):
            aa.xlsx_tables_to_payload(case_rows, orphan, metadata)

    def test_current_and_legacy_case_ids_must_be_globally_disjoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            codebook = load_fixture("synthetic_codebook.json")
            source = load_fixture("synthetic_master.json")
            old_uid = codebook["reused_records"][0]["post_case_uid"]
            codebook_row = codebook["reused_records"][0]
            codebook_row["post_case_uid"] = "SYN-PRE-A"
            legacy_source_row = next(
                row for row in source["cases"] if row.get("post_case_uid") == old_uid
            )
            legacy_source_row["post_case_uid"] = "SYN-PRE-A"
            new_fingerprint = aa.canonical_post_content_fingerprint(legacy_source_row)
            legacy_source_row["post_content_fingerprint"] = new_fingerprint
            codebook_row["post_content_fingerprint"] = new_fingerprint
            catalog = load_fixture("synthetic_post_identity_catalog.json")
            next(
                row for row in catalog["post_presentations"]
                if row["post_case_uid"] == old_uid
            )["post_case_uid"] = "SYN-PRE-A"
            source_path = out / "master.json"
            write_temp(source_path, source)
            write_temp(out / "synthetic_post_identity_catalog.json", catalog)
            codebook["source_master"] = str(source_path.resolve())
            codebook_path = out / "codebook.json"
            write_temp(codebook_path, codebook)
            with self.assertRaisesRegex(aa.ValidationError, "globally disjoint"):
                aa.load_layout(SYN_MANIFEST, codebook_path, SYN_TRANSLATIONS)

    def test_endpoint_metrics_follow_frozen_actual_availability(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            frozen, _, _, _ = self.freeze_synthetic(out)
            current = next(case for case in frozen["cases"] if case["stratum"] == "pre18")
            current["endpoint_node_ids"] = [current["node_universe"][0]]
            frozen = aa.seal(frozen, "label_bundle_sha256")
            frozen_path = out / "bad_endpoint_frozen.json"
            write_temp(frozen_path, frozen)
            system = load_fixture("synthetic_system_outputs.template.json")
            system["label_bundle_sha256"] = frozen["label_bundle_sha256"]
            system_path = out / "system.json"
            write_temp(system_path, system)
            with self.assertRaisesRegex(aa.ValidationError, "availability flag is inconsistent"):
                aa.score_system_outputs(
                    frozen_path, system_path, bootstrap_samples=20, seed=1,
                    require_complete_grid=False,
                )

    def test_freeze_recomputes_merged_from_all_three_bound_exports(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            paths = self.merge_synthetic(out)
            merged = aa.read_json(paths["merged"])
            merged["cases"][0]["provisional"]["target_conflict"] = "present"
            merged = aa.seal(merged)
            tampered_path = out / "tampered_resealed_merged.json"
            write_temp(tampered_path, merged)
            adjudication_path = self.bound_adjudication(merged, out)
            with self.assertRaisesRegex(aa.ValidationError, "fresh recomputation"):
                aa.freeze_labels(
                    tampered_path, adjudication_path, SYN_MANIFEST, SYN_CODEBOOK,
                    SYN_TRANSLATIONS, SYN_LEGACY, **self.freeze_options(),
                )

    def test_freeze_records_recomputed_iaa_queue_and_source_exports(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            frozen, _, paths, _ = self.freeze_synthetic(out)
            self.assertEqual(
                frozen["source_artifacts"]["recomputed_iaa_artifact_sha256"],
                aa.read_json(paths["iaa"])["artifact_sha256"],
            )
            self.assertEqual(
                frozen["source_artifacts"]["recomputed_adjudication_queue_artifact_sha256"],
                aa.read_json(paths["adjudication"])["artifact_sha256"],
            )
            self.assertEqual(
                {row["expert_id"] for row in frozen["source_artifacts"]["source_exports"]},
                set(aa.EXPERT_IDS),
            )

    def test_adjudication_metadata_is_recomputed_not_trusted(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            paths = self.merge_synthetic(out)
            merged = aa.read_json(paths["merged"])
            adjudication = load_fixture("synthetic_adjudication_filled.json")
            adjudication["merged_artifact_sha256"] = merged["artifact_sha256"]
            adjudication["cases"][0]["provisional_2_of_3"]["confidence_median"] = 5
            adjudication = aa.seal(adjudication)
            adjudication_path = out / "tampered_metadata.json"
            write_temp(adjudication_path, adjudication)
            with self.assertRaisesRegex(aa.ValidationError, "metadata provisional_2_of_3"):
                aa.freeze_labels(
                    paths["merged"], adjudication_path, SYN_MANIFEST, SYN_CODEBOOK,
                    SYN_TRANSLATIONS, SYN_LEGACY, **self.freeze_options(),
                )

    def test_post_fingerprint_is_recomputed_from_canonical_node_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            source = load_fixture("synthetic_master.json")
            codebook = load_fixture("synthetic_codebook.json")
            source_row = next(row for row in source["cases"] if row.get("post_case_uid") == "syn-post-new-a-uid")
            codebook_row = next(row for row in codebook["records"] if row["presentation_id"] == "SYN-POST-A")["master_record"]
            source_row["nodes"][0]["content"] = "Tampered canonical text."
            codebook_row["nodes"][0]["content"] = "Tampered canonical text."
            source_path = out / "synthetic_master.json"
            write_temp(source_path, source)
            write_temp(out / "synthetic_post_identity_catalog.json", load_fixture("synthetic_post_identity_catalog.json"))
            codebook["source_master"] = str(source_path.resolve())
            codebook_path = out / "codebook.json"
            write_temp(codebook_path, codebook)
            with self.assertRaisesRegex(aa.ValidationError, "differs from canonical node text"):
                aa.load_layout(SYN_MANIFEST, codebook_path, SYN_TRANSLATIONS)

    def test_wrapper_is_bound_to_its_exact_master_case(self):
        with tempfile.TemporaryDirectory() as temporary:
            codebook = load_fixture("synthetic_codebook.json")
            codebook["source_master"] = str(SYN_MASTER.resolve())
            left = codebook["records"][2]["master_record"]
            right = codebook["records"][3]["master_record"]
            codebook["records"][2]["master_record"] = right
            codebook["records"][3]["master_record"] = left
            path = Path(temporary) / "swapped_wrappers.json"
            write_temp(path, codebook)
            with self.assertRaisesRegex(aa.ValidationError, "original_case_id does not bind"):
                aa.load_layout(SYN_MANIFEST, path, SYN_TRANSLATIONS)

    def test_section_to_node_mapping_must_be_one_to_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            codebook = load_fixture("synthetic_codebook.json")
            codebook["source_master"] = str(SYN_MASTER.resolve())
            codebook["records"][0]["section_map"][1]["original_node_id"] = "syn-pre-a-n1"
            path = Path(temporary) / "many_to_one.json"
            write_temp(path, codebook)
            with self.assertRaisesRegex(aa.ValidationError, "not one-to-one"):
                aa.load_layout(SYN_MANIFEST, path, SYN_TRANSLATIONS)

    def test_legacy_source_schema_locator_and_record_are_verified(self):
        layout = self.synthetic_layout()
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            unsupported_source = out / "unsupported_source.json"
            write_temp(unsupported_source, {"schema_version": "arbitrary.v1", "records": []})
            unsupported = load_fixture("synthetic_legacy_labels.json")
            unsupported["source_artifact_path"] = str(unsupported_source)
            unsupported["source_artifact_sha256"] = aa.file_sha256(unsupported_source)
            unsupported_path = out / "unsupported_labels.json"
            write_temp(unsupported_path, unsupported)
            with self.assertRaisesRegex(aa.ValidationError, "supported formal source-record schema"):
                aa.load_legacy_labels(unsupported_path, layout)

            source = load_fixture("synthetic_legacy_source.json")
            source["records"][0]["final_need_more_context"] = "yes"
            source_path = out / "changed_source_record.json"
            write_temp(source_path, source)
            changed = load_fixture("synthetic_legacy_labels.json")
            changed["source_artifact_path"] = str(source_path)
            changed["source_artifact_sha256"] = aa.file_sha256(source_path)
            changed_path = out / "changed_labels.json"
            write_temp(changed_path, changed)
            with self.assertRaisesRegex(aa.ValidationError, "differs from resolved source record"):
                aa.load_legacy_labels(changed_path, layout)

            unresolved = load_fixture("synthetic_legacy_labels.json")
            unresolved["source_artifact_path"] = str(SYN_LEGACY_SOURCE.resolve())
            unresolved["cases"][0]["source_record_locator"] = "missing-row"
            unresolved_path = out / "unresolved_locator.json"
            write_temp(unresolved_path, unresolved)
            with self.assertRaisesRegex(aa.ValidationError, "does not resolve"):
                aa.load_legacy_labels(unresolved_path, layout)

    def test_system_output_requires_exact_case_uid_and_post_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            frozen, frozen_path, _, _ = self.freeze_synthetic(out)
            base = load_fixture("synthetic_system_outputs.template.json")
            base["label_bundle_sha256"] = frozen["label_bundle_sha256"]
            variants = [
                ("missing_uid", lambda row: row.pop("case_uid"), "exact case_uid is required"),
                ("wrong_uid", lambda row: row.__setitem__("case_uid", "sibling-uid"), "case_uid mismatch"),
                ("missing_fingerprint", lambda row: row.pop("post_content_fingerprint"), "post_content_fingerprint field is required"),
                ("wrong_fingerprint", lambda row: row.__setitem__("post_content_fingerprint", "sha256:" + "0" * 64), "post_content_fingerprint mismatch"),
            ]
            for name, mutate, error in variants:
                with self.subTest(name=name):
                    payload = copy.deepcopy(base)
                    mutate(payload["records"][2])
                    path = out / f"{name}.json"
                    write_temp(path, payload)
                    with self.assertRaisesRegex(aa.ValidationError, error):
                        aa.score_system_outputs(
                            frozen_path, path, bootstrap_samples=20, seed=1,
                            require_complete_grid=True,
                        )

    def test_gwet_ac1_uses_fixed_category_universe_numeric_oracle(self):
        units = [("a", "a", "b"), ("a", "b", "b")]
        observed_only = aa.nominal_multi_rater(units, ["a", "b"])
        fixed_three = aa.nominal_multi_rater(units, ["a", "b", "c"])
        self.assertAlmostEqual(observed_only["gwet_ac1_nominal"], -1 / 3)
        self.assertAlmostEqual(fixed_three["gwet_ac1_nominal"], 1 / 9)
        self.assertEqual(fixed_three["label_counts"]["c"], 0)

    def test_minimal_evidence_must_be_subset_of_repair(self):
        layout = self.synthetic_layout()
        payload = load_fixture("synthetic_expert_1.json")
        section = payload["annotations"]["SYN-POST-A"]["sections"]["S001"]
        section["minimal_evidence"] = True
        section["repair_packet"] = False
        with self.assertRaisesRegex(aa.ValidationError, "subset of the repair packet"):
            aa.validate_expert_export(payload, layout, Path("synthetic_bad.json"))
        with self.assertRaisesRegex(aa.ValidationError, "subset of the repair packet"):
            aa._validate_final_fields(
                "present", "yes", "no", ["n1"], ["n2"], {"n1", "n2"}, "synthetic"
            )

    def test_bridge_aware_cleanliness_uses_frozen_canonical_bridge(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            frozen, frozen_path, _, _ = self.freeze_synthetic(out)
            legacy = next(case for case in frozen["cases"] if case["case_id"] == "syn-legacy-a-uid")
            self.assertEqual(legacy["bridge_node_ids"], ["syn-legacy-a-n3"])
            self.assertEqual(
                set(legacy["bridge_aware_allowed_node_ids"]),
                {"syn-legacy-a-n1", "syn-legacy-a-n2", "syn-legacy-a-n3"},
            )
            self.assertEqual(
                frozen["score_protocol"]["endpoint_metric_scope"],
                ["post_new24", "post_legacy12"],
            )
            system = load_fixture("synthetic_system_outputs.template.json")
            system["label_bundle_sha256"] = frozen["label_bundle_sha256"]
            row = next(item for item in system["records"] if item["case_id"] == "syn-legacy-a-uid")
            row["returned_node_ids"] = ["syn-legacy-a-n3"]
            path = out / "bridge_only.json"
            write_temp(path, system)
            cleanliness, _ = aa.score_system_outputs(
                frozen_path, path, bootstrap_samples=20, seed=1,
                require_complete_grid=True,
            )
            scored = next(item for item in cleanliness["records"] if item["case_id"] == "syn-legacy-a-uid")
            self.assertEqual(scored["excess_node_rate"], 1.0)
            self.assertEqual(scored["bridge_aware_excess_node_rate"], 0.0)
            self.assertEqual(scored["bridge_aware_precision"], 1.0)

    def test_set_jaccard_reports_eligible_conditional_value(self):
        cases = [
            {"annotations": {expert: {"minimal": []} for expert in aa.EXPERT_IDS}},
            {"annotations": {
                "expert_1": {"minimal": ["x"]},
                "expert_2": {"minimal": []},
                "expert_3": {"minimal": []},
            }},
        ]
        result = aa.set_iaa(cases, "minimal")
        self.assertAlmostEqual(result["mean_pairwise_jaccard"], 2 / 3)
        self.assertEqual(result["eligible_pair_case_count"], 2)
        self.assertEqual(result["eligible_conditional_mean_pairwise_jaccard"], 0.0)

    def test_cluster_bootstrap_is_scc_equal_weighted_and_deterministic(self):
        rows = [
            {"source_scc_uid": "A", "metric": 0.0},
            {"source_scc_uid": "A", "metric": 0.0},
            {"source_scc_uid": "A", "metric": 0.0},
            {"source_scc_uid": "B", "metric": 1.0},
        ]
        first = aa.cluster_bootstrap_ci(rows, "metric", samples=500, seed=9)
        second = aa.cluster_bootstrap_ci(copy.deepcopy(rows), "metric", samples=500, seed=9)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0.5)
        self.assertEqual(first[3:], (4, 2))


class BinaryAnnotationContractTests(unittest.TestCase):
    """All records here are in-memory synthetic examples, never expert evidence."""

    @staticmethod
    def record(target="present", sufficient="yes"):
        return {
            "synthetic_fixture": True,
            "annotation_protocol": aa.BINARY_PROTOCOL,
            "target_conflict": target,
            "judgment_sufficient": sufficient,
            "sets_reviewed": True,
            "confidence": 4,
            "sections": {
                "S1": {"minimal_evidence": target == "present", "repair_packet": target == "present"},
                "S2": {"minimal_evidence": False, "repair_packet": target == "present"},
                "S3": {"minimal_evidence": False, "repair_packet": False},
            },
        }

    def test_binary_sufficient_negative_enters_fpr_denominator(self):
        row = aa.binary_case_metrics(
            self.record("absent"), {"S1", "S2", "S3"}, [], prediction="present", output_valid=True,
        )
        self.assertEqual(row["scoring_status"], "negative")
        self.assertTrue(row["false_positive_denominator_eligible"])
        self.assertEqual(row["over_reported"], 1.0)
        self.assertIsNone(row["expert_evidence_recall"])

    def test_insufficient_raw_negative_and_positive_enter_neither_denominator(self):
        for target in ("present", "absent"):
            with self.subTest(target=target):
                row = aa.binary_case_metrics(
                    self.record(target, "no"), {"S1", "S2", "S3"}, [],
                    prediction="present", output_valid=True,
                )
                self.assertEqual(row["target_conflict"], target)
                self.assertEqual(row["judgment_sufficient"], "no")
                self.assertEqual(row["scoring_status"], "insufficient")
                self.assertTrue(row["requires_adjudication"])
                for key in ("positive_denominator_eligible", "negative_denominator_eligible", "false_positive_denominator_eligible"):
                    self.assertFalse(row[key])
                for key in ("over_reported", "positive_detection_hit", "expert_evidence_recall", "excess_node_rate"):
                    self.assertIsNone(row[key])

    def test_no_role_or_context_is_required_or_manufactured(self):
        record = self.record()
        normalized = aa.validate_binary_annotation(record, {"S1", "S2", "S3"})
        self.assertNotIn("role", normalized["sections"]["S1"])
        self.assertNotIn("need_more_context", normalized)
        self.assertNotIn("evidence_sufficient", normalized)
        self.assertNotIn("scoring_status", record)
        for field in ("role", "need_more_context", "evidence_sufficient"):
            self.assertEqual(aa.binary_categorical_iaa([], field)["rating_count"], 0)

    def test_legacy_labels_remain_verbatim_but_are_not_new_iaa_ratings(self):
        record = self.record()
        record["evidence_sufficient"] = "partial"
        record["need_more_context"] = "uncertain"
        record["sections"]["S1"]["role"] = "conflict_evidence"
        normalized = aa.validate_binary_annotation(record, {"S1", "S2", "S3"})
        self.assertEqual(normalized["evidence_sufficient"], "partial")
        self.assertEqual(normalized["need_more_context"], "uncertain")
        self.assertEqual(normalized["sections"]["S1"]["role"], "conflict_evidence")
        case = {"section_ids": ["S1", "S2", "S3"], "annotations": {expert: record for expert in aa.EXPERT_IDS}}
        self.assertEqual(aa.binary_categorical_iaa([case], "role")["n_units"], 0)
        self.assertEqual(aa.binary_categorical_iaa([case], "judgment_sufficient")["rating_count"], 3)
        del case["annotations"]["expert_3"]
        self.assertEqual(aa.binary_categorical_iaa([case], "judgment_sufficient")["excluded_incomplete_units"], 1)

    def test_drafts_and_old_sufficiency_cannot_become_binary_completion(self):
        for modification in (
            {"sets_reviewed": False}, {"sets_reviewed": None},
            {"judgment_sufficient": "partial"}, {"judgment_sufficient": "not_applicable"},
            {"judgment_sufficient": None, "evidence_sufficient": "yes"},
            {"confidence": 2.5}, {"confidence": True}, {"annotation_protocol": None},
        ):
            with self.subTest(modification=modification):
                record = {**self.record(), **modification}
                with self.assertRaises(aa.ValidationError):
                    aa.validate_binary_annotation(record, {"S1", "S2", "S3"})

    def test_positive_needs_explicit_evidence_subset_of_repair(self):
        record = self.record()
        record["sections"]["S1"]["repair_packet"] = False
        with self.assertRaisesRegex(aa.ValidationError, "subset"):
            aa.validate_binary_annotation(record, {"S1", "S2", "S3"})
        record["sections"]["S1"]["minimal_evidence"] = False
        with self.assertRaisesRegex(aa.ValidationError, "requires minimal"):
            aa.validate_binary_annotation(record, {"S1", "S2", "S3"})
        record["sections"]["S2"]["repair_packet"] = "false"
        with self.assertRaisesRegex(aa.ValidationError, "explicit booleans"):
            aa.validate_binary_annotation(record, {"S1", "S2", "S3"})

    def test_single_case_quality_and_declared_bridge_allowance(self):
        row = aa.binary_case_metrics(
            self.record(), {"S1", "S2", "S3"}, ["S1", "S3"],
            prediction="present", output_valid=True, bridge_section_ids=["S3"],
        )
        self.assertEqual(row["expert_evidence_recall"], 1.0)
        self.assertEqual(row["repair_packet_coverage"], 0.5)
        self.assertEqual(row["excess_node_rate"], 0.5)
        self.assertEqual(row["bridge_aware_excess_node_rate"], 0.0)
        self.assertEqual(row["bridge_aware_precision"], 1.0)
        self.assertEqual(row["expert_evidence_density"], 0.5)
        self.assertIsNone(row["over_reported"])

    def test_invalid_and_empty_return_keep_positive_denominators(self):
        row = aa.binary_case_metrics(
            self.record(), {"S1", "S2", "S3"}, [], prediction="invalid", output_valid=False,
        )
        self.assertTrue(row["positive_denominator_eligible"])
        self.assertEqual(row["strict_valid"], 0.0)
        for key in ("expert_evidence_recall", "repair_packet_coverage", "excess_node_rate", "bridge_aware_precision"):
            self.assertEqual(row[key], 0.0)
        with self.assertRaisesRegex(aa.ValidationError, "outside"):
            aa.binary_case_metrics(self.record(), {"S1", "S2", "S3"}, ["WRONG"], prediction="present", output_valid=True)

    def test_new_protocol_and_assisted_json_cannot_enter_legacy_blind_merge(self):
        layout = aa.load_layout(SYN_MANIFEST, SYN_CODEBOOK, SYN_TRANSLATIONS)
        payload = load_fixture("synthetic_expert_1.json")
        payload["annotation_mode"] = "method_assisted_review"
        with self.assertRaisesRegex(aa.ValidationError, "annotation_mode"):
            aa.validate_expert_export(payload, layout, Path("synthetic.json"))
        payload["annotation_mode"] = "blind_human_audit"
        payload["annotation_protocol"] = aa.BINARY_PROTOCOL
        with self.assertRaisesRegex(aa.ValidationError, "explicit annotation protocol"):
            aa.validate_expert_export(payload, layout, Path("synthetic.json"))
        del payload["annotation_protocol"]
        next(iter(payload["annotations"].values()))["annotation_protocol"] = aa.BINARY_PROTOCOL
        with self.assertRaisesRegex(aa.ValidationError, "explicit annotation protocol"):
            aa.validate_expert_export(payload, layout, Path("synthetic.json"))

    def test_assisted_xlsx_and_new_protocol_cannot_be_laundered_into_blind_v2(self):
        for field, value in (
            ("annotation_mode", "method_assisted_review"),
            ("标注模式", "带算法提示的辅助复核"),
            ("hint_pack_hash", "sha256:synthetic-only"),
            ("annotation_protocol", aa.BINARY_PROTOCOL),
        ):
            for sheet_index in (0, 1, 2):
                with self.subTest(field=field, sheet=sheet_index):
                    tables = AnnotationAnalysisTests.xlsx_tables()
                    tables[sheet_index][0][field] = value
                    with self.assertRaises(aa.ValidationError):
                        aa.xlsx_tables_to_payload(*tables)


if __name__ == "__main__":
    unittest.main()
