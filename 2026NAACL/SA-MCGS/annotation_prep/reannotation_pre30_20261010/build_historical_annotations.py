#!/usr/bin/env python3
"""Map the two original experts' frozen XLSX answers onto the 18 pre cases.

Read-only extraction: original independent votes, never adjudicated final labels.
The current page's mode is separate from original export metadata/attestation.
"""
import hashlib
import importlib.util
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
PREP = HERE.parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_history(cases):
    spec = importlib.util.spec_from_file_location("historical_review_reader", PREP / "third_expert_review/build_review.py")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    manifest = read(PREP / "frontend/data/manifest.json")
    audit = read(PREP / "third_expert_review/internal/selection_audit.json")
    codebook = read(PREP / "internal/private_codebook.json")
    assert manifest["manifest_hash"] == audit["parent_manifest_hash"]
    old_cases = {c["presentation_id"]: c for c in manifest["cases"]}
    originals = {r["master_record"]["pre_source_id"]: r for r in codebook["records"]
                 if r["master_record"].get("pre_source_id") and r["master_record"].get("unmodified")}
    decisions = {r["presentation_id"]: r for r in audit["decisions"]}
    assert len(cases) == 18 and len(originals) == 18
    pack = {"schema_version": "pre18_historical_annotations.v1",
            "protocol": "two_independent_experts_plus_targeted_third_review",
            "source_manifest_hash": manifest["manifest_hash"],
            "author_blinding_attestation": audit["author_blinding_attestation"],
            "timestamp_semantics": "Historical confirmed_at/updated_at reuse the original XLSX 保存时间; they do not mark a new confirmation or claim a separately recorded historical confirmation time.",
            "experts": {}}
    report = {}
    for frozen in audit["inputs"]:
        slot = frozen["expert_slot"]
        assert slot in ("expert_1", "expert_2")
        source = Path(frozen["path"])
        assert hashlib.sha256(source.read_bytes()).hexdigest() == frozen["sha256"], source
        votes, checked_source = reader.read_expert(source, manifest, slot)
        assert checked_source == frozen
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
        try:
            rows = {r["样本编号"]: r for r in reader.records(workbook["样本整体标注"])}
            paragraphs = {(r["样本编号"], r["段落编号"]): r for r in reader.records(workbook["逐段标注"])}
        finally:
            workbook.close()
        annotations, provenance = {}, {}
        for case in cases:
            original = originals[case["pre_source_id"]]
            master = original["master_record"]
            assert master["unmodified"] is True
            assert master["source_physical_fingerprint"] == case["source_physical_fingerprint"]
            assert master["pre_content_fingerprint"] == case["content_hash"]
            pid = original["presentation_id"]
            vote, row = votes[pid], rows[pid]
            assert vote == decisions[pid][slot]
            old_sections = {s["section_id"]: s for s in old_cases[pid]["sections"]}
            by_node = {s["original_node_id"]: s["section_id"] for s in original["section_map"]}
            assert len(by_node) == len(case["sections"])
            assert set(by_node) == {s["source_node_id"] for s in case["sections"]}
            mapping, sections, original_sections = [], {}, {}
            for section in case["sections"]:
                old_sid = by_node[section["source_node_id"]]
                assert section["original_text"].strip() == old_sections[old_sid]["text"]
                original_row = paragraphs[(pid, old_sid)]
                assert (original_row["原文正文"] or "") == old_sections[old_sid]["text"]
                sections[section["id"]] = {"minimal_evidence": old_sid in vote["minimal_evidence_section_ids"],
                                          "repair_material": old_sid in vote["repair_packet_section_ids"]}
                assert not sections[section["id"]]["minimal_evidence"] or sections[section["id"]]["repair_material"]
                original_sections[old_sid] = {k: original_row[k] for k in (
                    "是否最小证据", "是否修复材料", "段落备注", "annotation_mode", "annotation_protocol",
                    "hints_visible", "progress_origin", "_xlsx_row")}
                mapping.append({"source_section_id": old_sid, "section_id": section["id"],
                                "source_node_id": section["source_node_id"]})
            saved = row["保存时间"]
            assert isinstance(saved, str) and datetime.fromisoformat(saved.replace("Z", "+00:00")).tzinfo
            notes = row["整体备注"]
            assert notes is None or isinstance(notes, str)
            record = {"case_id": case["id"], "content_hash": case["content_hash"],
                      "target_conflict": vote["target_conflict"],
                      "judgment_sufficient": {"yes": "sufficient", "no": "insufficient"}[vote["judgment_sufficient"]],
                      "confidence": vote["confidence"], "sections": sections, "notes": notes or "",
                      "confirmed": True, "sets_reviewed": True, "confirmed_at": saved,
                      "updated_at": saved, "sa_visible": True}
            annotations[case["id"]] = record
            provenance[case["id"]] = {
                "source_presentation_id": pid, "pre_source_id": case["pre_source_id"],
                "source_content_hash": case["content_hash"], "source_saved_at": saved,
                "source_annotation_mode": row["annotation_mode"],
                "source_annotation_protocol": row["annotation_protocol"],
                "source_xlsx_row": row["_xlsx_row"],
                "original_record": {**row, "sections": original_sections}, "section_mapping": mapping,
                "current_page_sa_visible_is_not_historical_exposure": True}
        pack["experts"][slot] = {"annotations": annotations,
            "provenance": {"source_file": source.name, "source_sha256": "sha256:" + frozen["sha256"],
                           "source_manifest_hash": manifest["manifest_hash"], "expert_slot": slot,
                           "export_metadata": frozen["export_metadata"],
                           "author_blinding_attestation": audit["author_blinding_attestation"],
                           "timestamp_semantics": pack["timestamp_semantics"]},
            "case_provenance": provenance}
        report[slot] = {"case_count": len(annotations), "section_count": sum(len(r["sections"]) for r in annotations.values()),
                        "target_conflict": dict(Counter(r["target_conflict"] for r in annotations.values())),
                        "judgment_sufficient": dict(Counter(r["judgment_sufficient"] for r in annotations.values())),
                        "nonempty_case_notes": sum(bool(r["notes"]) for r in annotations.values()),
                        "nonempty_section_notes": sum(bool(s["段落备注"]) for r in provenance.values() for s in r["original_record"]["sections"].values()),
                        "source_sha256": frozen["sha256"]}
    assert set(pack["experts"]) == {"expert_1", "expert_2"}
    pack["pack_hash"] = digest(pack)
    audit_path = HERE / "qa/historical_annotations_audit.json"
    audit_path.parent.mkdir(exist_ok=True)
    audit_path.write_text(json.dumps({"pack_hash": pack["pack_hash"], "experts": report,
        "all_original_votes_match_frozen_audit": True, "all_original_source_and_section_texts_match": True,
        "third_expert_seeded": False, "adjudicated_final_labels_used": False,
        "model_calls": 0}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pack


if __name__ == "__main__":
    result = build_history(read(HERE / "payload.json")["cases"])
    print(json.dumps({"pack_hash": result["pack_hash"], "experts": {k: len(v["annotations"]) for k, v in result["experts"].items()}}, indent=2))
