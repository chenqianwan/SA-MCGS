#!/usr/bin/env python3
"""Build the pre18 payload with original expert answers for a partial revision."""
import argparse
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
from build_historical_annotations import build_history

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
PAPER = PREP.parent
LABELS = {"gpt-4o": "GPT-4o", "gemini-2.5-pro": "Gemini 2.5 Pro", "qwen3.5-9b": "Qwen3.5-9B"}
DOMAINS = {"sec_ex21": "公司披露 · SEC", "bgb": "德国民法 · BGB", "cuad": "合同 · CUAD"}

# Keep per-node scores, ranking and deployable-core selection identical to the
# previous assisted annotation page. Import definitions only, not its main build.
_spec = importlib.util.spec_from_file_location("pre30_hint_helpers", PREP / "frontend/tools/build_method_hints.py")
_hints = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hints)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def historical_predictions(model):
    if model not in ("gpt-4o", "gemini-2.5-pro"):
        return {}
    alias = "gpt" if model == "gpt-4o" else "gemini"
    first = PAPER / f"experiments/sa_runs/sa_pre_{alias}18_20260829/results"
    retry = PAPER / "experiments/pre_baseline_runs/pre_baseline_v1_20260909" / ("sa_retry_gpt10/results" if alias == "gpt" else "sa_retry_gemini14/results")
    results = {}
    for path in sorted(first.glob("*.json")):
        result = read(path)
        assert result["model"] == model
        results[result["pre_source_id"]] = (path, result)
    for path in sorted(retry.glob("*.json")):
        result = read(path)
        previous = results[result["pre_source_id"]][1]
        assert previous["target_conflict_decision"] == "invalid"
        assert result["case_uid"] == previous["case_uid"]
        assert result["model"] == model
        results[result["pre_source_id"]] = (path, result)
    return results


def historical_lea(model):
    if model not in ("gpt-4o", "gemini-2.5-pro"):
        return {}
    alias = "gpt" if model == "gpt-4o" else "gemini"
    directory = PAPER / f"experiments/lea_runs/lea_pre_{alias}18_20260829/results"
    results = {}
    for path in sorted(directory.glob("*.json")):
        result = read(path)
        assert result["model"] == model and result["method"] == "lea"
        assert result["pre_source_id"] not in results
        results[result["pre_source_id"]] = (path, result)
    return results


def node_hints(source, method, model, saved, section_map):
    if saved is None:
        hint = _hints.unavailable_hint("not_run", "此未注入案例尚未运行该方法，暂无逐节点结果。")
        return {section: dict(hint) for section in section_map.values()}, {"status": "not_run"}
    path, result = saved
    assert result["method"] == method and result["model"] == model
    assert result["condition"] == "pre" and result["inject_mode"] is False and result["unmodified"] is True
    for key in ("source_physical_fingerprint", "pre_content_fingerprint", "dataset_revision", "pre_source_id", "domain"):
        assert result[key] == source[key], (path, key)
    assert result["scc_clause_ids"] == source["ordered_clause_ids"], path
    invalid = bool(result.get("cost_audit_error"))
    assert invalid == (result.get("target_conflict_decision") == "invalid")
    hints = {section: _hints.strict_invalid_hint(result) if invalid else
             _hints.compact_hint(result, method, node, set(section_map))
             for node, section in section_map.items()}
    if method == "sa-mcgs" and "pre_baseline_v1_20260909" in path.parts:
        for hint in hints.values():
            _hints.add_retry_provenance(hint, {"_hint_source_attempt": "retry_20260909"})
    provenance = {"status": "strict_invalid" if invalid else "available", "condition": "pre",
                  "method": method, "model": model, "pre_source_id": source["pre_source_id"],
                  "pre_content_fingerprint": source["pre_content_fingerprint"],
                  "result_path": str(path.relative_to(PAPER)),
                  "result_sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()}
    return hints, provenance


def prediction_card(source, model, saved, section_map):
    base = {"model": model, "label": LABELS.get(model, model)}
    if saved is None:
        return {**base, "status": "pending", "risk_found": None, "risk_pair_count": None,
                "reason": "此原文案例尚无该模型的 SA 结果，不能记为无风险。", "evidence_sections": []}
    path, result = saved
    assert result["model"] == model and result["method"] == "sa-mcgs"
    assert result["condition"] == "pre" and result["inject_mode"] is False and result["unmodified"] is True
    for key in ("source_physical_fingerprint", "pre_content_fingerprint", "dataset_revision", "pre_source_id"):
        assert result[key] == source[key], (path, key)
    assert list(result["scc_clause_ids"]) == source["ordered_clause_ids"], path
    decision = result["target_conflict_decision"]
    assert decision in ("invalid", "assert_target_conflict", "abstain_from_target_conflict")
    assert (decision == "invalid") == bool(result.get("cost_audit_error"))
    pairs = result.get("explicit_conflict_pairs", [])
    if decision != "invalid":
        assert bool(pairs) == (decision == "assert_target_conflict")
    mapped = []
    for pair in pairs:
        assert pair["source"] != pair["target"]
        assert pair["source"] in section_map and pair["target"] in section_map
        assert str(pair.get("reason") or pair.get("reasoning") or "").strip(), pair
        mapped.append({"source": section_map[pair["source"]], "target": section_map[pair["target"]],
                       "reason": pair.get("reason") or pair.get("reasoning")})
    invalid = decision == "invalid"
    return {**base, "status": "invalid" if invalid else "available",
            "risk_found": None if invalid else decision == "assert_target_conflict",
            "risk_pair_count": None if invalid else len(pairs),
            "reason": "运行或输出校验失败，不能记为无风险。" if invalid else
                      ("SA 在搜索过程中报告了明确的冲突条款对；是否确有冲突由本次人工重新判断。" if pairs else "SA 未报告符合规则的明确冲突条款对。"),
            "evidence_sections": sorted({section_map[p[k]] for p in pairs for k in ("source", "target")}),
            "conflict_pairs": mapped,
            "decision_rule": result.get("abstention_rule_version", "explicit_pair_v1"),
            "target_conflict_decision": decision,
            "result_sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            "result_path": str(path.relative_to(PAPER)),
            "sa_protocol_fingerprint": result.get("sa_protocol_fingerprint"),
            "completed_at": result.get("audit_completed_at")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", default=["gpt-4o", "gemini-2.5-pro"])
    parser.add_argument("--result-dir", type=Path, action="append", default=[])
    parser.add_argument("--lea-result-dir", type=Path, action="append", default=[])
    args = parser.parse_args()
    assert len(set(args.models)) == len(args.models)
    sources = read(HERE / "sources_main18.json")
    assert len(sources) == 18 and len({s["source_physical_fingerprint"] for s in sources}) == 18
    assert len({(s["domain"], tuple(sorted(s["ordered_clause_ids"]))) for s in sources}) == 18
    seen_nodes = collections.defaultdict(set)
    for source in sources:
        assert not seen_nodes[source["domain"]].intersection(source["ordered_clause_ids"])
        seen_nodes[source["domain"]].update(source["ordered_clause_ids"])
    assert collections.Counter(s["domain"] for s in sources) == {"sec_ex21": 5, "bgb": 3, "cuad": 10}
    old = read(PREP / "candidates/pre_sources_18.json")
    assert sources == old
    main_plan = read(PAPER / "validation/identity_stage2_80/case_plan.json")
    main_sources = {(r["domain"], tuple(sorted(r["planned_case_identity"]["ordered_clause_ids"]))) for r in main_plan}
    current_sources = {(r["domain"], tuple(sorted(r["ordered_clause_ids"]))) for r in sources}
    assert len(main_plan) == 80 and len(main_sources) == 20
    assert current_sources == {key for key in main_sources if key[0] != "debian"}
    old_cases = {c["presentation_id"]: c for c in read(PREP / "frontend/data/manifest.json")["cases"]}
    old_map = {r["master_record"]["pre_source_id"]: r for r in read(PREP / "internal/private_codebook.json")["records"]
               if r["master_record"].get("pre_source_id") and r["master_record"].get("unmodified")}
    cache = read(PREP / "frontend/data/translation_cache_zh.json")["entries"]
    extra_path = HERE / "translations_new_zh.json"
    extra = read(extra_path).get("entries", {}) if extra_path.exists() else {}
    predictions = {model: historical_predictions(model) for model in args.models}
    lea_predictions = {model: historical_lea(model) for model in args.models}
    for directory in args.result_dir:
        for path in sorted(directory.glob("*.json")):
            result = read(path)
            model = result["model"]
            if model in predictions:
                predictions[model][result["pre_source_id"]] = (path, result)
    for directory in args.lea_result_dir:
        for path in sorted(directory.glob("*.json")):
            result = read(path)
            if result["model"] in lea_predictions:
                lea_predictions[result["model"]][result["pre_source_id"]] = (path, result)
    cases, missing, translated = [], {}, 0
    node_results, node_result_sources = {}, {}
    for index, source in enumerate(sources, 1):
        assert source["unmodified"] is True
        sections = []
        historical = {}
        record = old_map.get(source["pre_source_id"])
        if record:
            old_sections = {s["section_id"]: s for s in old_cases[record["presentation_id"]]["sections"]}
            historical = {r["original_node_id"]: old_sections[r["section_id"]] for r in record["section_map"]}
        for section_index, clause in enumerate(source["clauses"], 1):
            title = str(clause.get("title") or "")
            text = str(clause.get("content") or "")
            old_section = historical.get(clause["id"])
            if old_section:
                assert old_section["text"] == text.strip(), (source["pre_source_id"], clause["id"], "old text mismatch")
                translation_hash = digest({"title": old_section["title"], "text": old_section["text"]})
            else:
                translation_hash = digest({"title": title, "text": text})
            translation = cache.get(translation_hash) or extra.get(translation_hash)
            if not translation:
                missing[translation_hash] = {"hash": translation_hash, "title": title, "text": text,
                                            "domain": source["domain"], "source_id": source["pre_source_id"]}
            else:
                assert isinstance(translation["text_zh"], str) and translation["text_zh"].strip()
                translated += 1
            sections.append({"id": f"S{section_index:03d}", "source_node_id": clause["id"],
                             "heading": title, "original_text": text,
                             "zh_text": translation["text_zh"] if translation else None,
                             "zh_heading": translation["title_zh"] if translation else None,
                             "translation_source_hash": translation_hash if translation else None})
        mapping = {s["source_node_id"]: s["id"] for s in sections}
        case_id = f"PRE-{index:02d}"
        node_results[case_id] = {section: {"methods": {method: {"models": {}} for method in ("sa-mcgs", "lea")}}
                                 for section in mapping.values()}
        node_result_sources[case_id] = {}
        for method, saved_results in (("sa-mcgs", predictions), ("lea", lea_predictions)):
            node_result_sources[case_id][method] = {}
            for model in args.models:
                hints, provenance = node_hints(source, method, model, saved_results[model].get(source["pre_source_id"]), mapping)
                node_result_sources[case_id][method][model] = provenance
                for section, hint in hints.items():
                    node_results[case_id][section]["methods"][method]["models"][model] = hint
        cases.append({"id": f"PRE-{index:02d}", "order": index, "domain": source["domain"],
                      "source_label": DOMAINS[source["domain"]], "content_hash": source["pre_content_fingerprint"],
                      "source_physical_fingerprint": source["source_physical_fingerprint"],
                      "pre_source_id": source["pre_source_id"], "previous_batch": index <= 18,
                      "sections": sections,
                      "sa_predictions": [prediction_card(source, model, predictions[model].get(source["pre_source_id"]), mapping)
                                         for model in args.models]})
    payload = {"schema_version": "pre18_main_annotation_payload_v1", "study_id": "pre18_main_reannotation_20261010",
               "case_count": 18, "scope": "main_experiment_legal_sources_only",
               "main_experiment_source_count": 20, "excluded_main_domain": "debian",
               "annotation_mode": "method_assisted_reannotation", "sa_visible": True,
               "models": [{"id": model, "label": LABELS.get(model, model)} for model in args.models],
               "cases": cases,
               "risk_rule_description": "复用 explicit_pair_v1：搜索过程报告至少一对本案例内不同条款及非空冲突说明，即记为 SA 报告风险。不是人工结论，也不是分数阈值。"}
    payload["manifest_hash"] = digest([{k: v for k, v in case.items() if k != "sa_predictions"} for case in cases])
    payload["prediction_pack_hash"] = digest({c["id"]: c["sa_predictions"] for c in cases})
    # Keep original content/prediction identities stable so existing browser
    # annotations remain in the same storage slot. Node hints have their own hash.
    payload["node_results"] = node_results
    payload["node_result_sources"] = node_result_sources
    payload["method_hints_visible"] = ["sa-mcgs", "lea"]
    payload["node_results_pack_hash"] = digest({"results": node_results, "sources": node_result_sources})
    payload["predecessor"] = read(HERE / "predecessor_pre30.json")
    for case in cases:
        assert payload["predecessor"]["case_catalog"][case["id"]] == {
            "content_hash": case["content_hash"],
            "sections": [{"id": s["id"], "source_node_id": s["source_node_id"]} for s in case["sections"]]}
    payload["historical_annotations"] = build_history(cases)
    write(HERE / "payload.json", payload)
    write(HERE / "translations_missing.json", list(missing.values()))
    report = {"case_count": len(cases), "domains": dict(collections.Counter(c["domain"] for c in cases)),
              "sections": sum(len(c["sections"]) for c in cases), "translated_sections": translated,
              "missing_translation_unique": len(missing),
              "prediction_statuses": {m: dict(collections.Counter((p["status"] if p["risk_found"] is None else "risk" if p["risk_found"] else "no_risk")
                                          for c in cases for p in c["sa_predictions"] if p["model"] == m)) for m in args.models},
              "manifest_hash": payload["manifest_hash"], "prediction_pack_hash": payload["prediction_pack_hash"],
              "node_results_pack_hash": payload["node_results_pack_hash"],
              "historical_annotations_pack_hash": payload["historical_annotations"]["pack_hash"],
              "historical_experts": {slot: len(values["annotations"]) for slot, values in payload["historical_annotations"]["experts"].items()},
              "node_result_case_statuses": {method: {model: dict(collections.Counter(
                  node_result_sources[c["id"]][method][model]["status"] for c in cases)) for model in args.models}
                  for method in ("sa-mcgs", "lea")}}
    write(HERE / "payload_audit.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
