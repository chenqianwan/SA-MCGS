#!/usr/bin/env python3
"""Apply deterministic Chinese terminology normalization without new LLM calls."""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_translation_pack import build_output, load_json, source_hash, write_json


FRONTEND = Path(__file__).resolve().parents[1]
NORMALIZATION_VERSION = "legal_defined_terms_zh_v1"

BGB_DONOR_OVERRIDES = {
    "sha256:a8aa3d08dc4f6ad10bb28c0b4803ac86d9ff20586cbdd3c98b400755d6f02f88":
        "sha256:39ffbc56e20f74a55cd274ed1fc5c6c8d94f41ac4f04d4d3bd9d1fc81f2cd9d4",
    "sha256:09c2c92fa3732d1d6eb4558b5172c84126a2a24fc25de3b4a6e22a4571a33df7":
        "sha256:39b47f53c334e4b441f321fecbce60835ccee58dda8e713250b6704bab6b50d5",
}

GLOBAL_DEFINED_TERMS = {
    "IGER BACKGROUND INTELLECTUAL PROPERTY": "IGER 背景知识产权",
    "IGER INTELLECTUAL PROPERTY": "IGER 知识产权",
    "JOINT INTELLECTUAL PROPERTY": "联合知识产权",
    "OTHER RESEARCH RESULTS": "其他研究成果",
    "RESEARCH PROJECTS": "研究项目",
    "RESEARCH PROJECT": "研究项目",
    "COLLABORATION CROPS": "合作作物",
    "ADMINISTERING PARTY": "管理方",
    "RELEASED VARIETIES": "已发布品种",
}

FAMILY_TERMS = {
    ("P-0C44045D8E", "P-DF7F230F65"): {
        "SCHEDULES": "附表",
        "SCHEDULE": "附表",
        "EXHIBIT": "附件",
    },
    ("P-0A4D9A338A",): {
        "Regulatory Authorities": "监管机构",
        "Regulatory Approval": "监管批准",
        "Licensed Products": "许可产品",
        "Commercialization": "商业化",
        "Development": "开发",
        "Licensee": "被许可方",
        "Territory": "区域",
        "Field": "领域",
    },
    ("P-DE80BE0BC0",): {
        "AUTHORIZED SUBSIDIARIES": "获授权子公司",
        "Attachments": "附件",
        "Attachment": "附件",
        "Appendices": "附录",
        "Appendix": "附录",
        "Exhibits": "附件",
        "Exhibit": "附件",
        "Products": "产品",
        "Product": "产品",
        "Agreement": "协议",
        "Code": "代码",
    },
    ("P-1FD4239F47", "P-E0CD800287"): {
        "Advanced Pool Stock": "预置周转库存",
        "Used Serviceable Items": "可用旧件",
        "Security Deposit": "保证金",
        "The Company's": "公司的",
        "Company's": "公司的",
        "The Company": "公司",
        "Repairer": "维修方",
        "Company": "公司",
        "End Date": "终止日",
        "Law": "法律",
    },
    ("P-26A5621616", "P-6E178B900A", "P-4BAF2F94CC"): {
        "Marketing Contributions": "营销分摊款",
        "Competitive Business": "竞争业务",
        "Promissory Note": "本票",
        "Minimum Royalty": "最低特许权使用费",
        "Required Software": "必备软件",
        "Franchised Business": "特许经营业务",
        "Royalty Fee(s)": "特许权使用费",
        "Royalty Fees": "特许权使用费",
        "Royalty Fee": "特许权使用费",
        "Technology Fee(s)": "技术费",
        "Technology Fees": "技术费",
        "Technology Fee": "技术费",
        "Approved Location": "获准地点",
        "Gross Revenues": "总收入",
        "Net Revenues": "净收入",
        "Policy Fees": "保单费",
        "Month(s)": "月",
        "Managers": "管理人员",
        "Producers": "保险业务人员",
        "Premiums": "保费",
        "Manual": "手册",
        "Marks": "标识",
        "System": "系统",
    },
    ("P-9DE13FF061", "P-295AFF1987"): {
        "Aimmune Know-How": "Aimmune 专有技术",
        "Aimmune Patents": "Aimmune 专利",
        "Product(s)": "产品",
        "Products": "产品",
        "Product": "产品",
        "Patent(s)": "专利",
        "Patents": "专利",
        "Patent": "专利",
        "Invention": "发明",
    },
}


def replace_terms(text: str, rules: dict[str, str], counts: Counter[str]) -> str:
    value = text
    for source, target in sorted(rules.items(), key=lambda item: len(item[0]), reverse=True):
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(source)}(?![A-Za-z0-9])"
        )
        value, replacements = pattern.subn(target, value)
        if replacements:
            counts[f"{source} -> {target}"] += replacements
    return value


def hashes_for_prefixes(
    manifest: dict[str, Any], prefixes: tuple[str, ...]
) -> set[str]:
    hashes: set[str] = set()
    for case in manifest["cases"]:
        if not str(case["presentation_id"]).startswith(prefixes):
            continue
        for section in case["sections"]:
            hashes.add(
                source_hash(
                    str(section.get("title") or ""), str(section.get("text") or "")
                )
            )
    return hashes


def normalize(
    manifest: dict[str, Any], cache: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = copy.deepcopy(cache)
    entries = normalized["entries"]
    counts: Counter[str] = Counter()

    for target, donor in BGB_DONOR_OVERRIDES.items():
        if target not in entries or donor not in entries:
            raise RuntimeError(f"missing BGB normalization hash: {target} <- {donor}")
        changed = any(
            entries[target].get(field) != entries[donor].get(field)
            for field in ("title_zh", "text_zh")
        )
        for field in ("title_zh", "text_zh"):
            entries[target][field] = entries[donor][field]
        if changed:
            counts[f"BGB donor override {target}"] += 1

    for entry in entries.values():
        for field in ("title_zh", "text_zh"):
            entry[field] = replace_terms(
                str(entry.get(field) or ""), GLOBAL_DEFINED_TERMS, counts
            )

    for prefixes, rules in FAMILY_TERMS.items():
        for digest in hashes_for_prefixes(manifest, prefixes):
            entry = entries.get(digest)
            if not entry:
                raise RuntimeError(f"missing family translation hash: {digest}")
            for field in ("title_zh", "text_zh"):
                entry[field] = replace_terms(str(entry.get(field) or ""), rules, counts)

    numeric_hash = source_hash(
        next(
            section
            for case in manifest["cases"]
            if case["presentation_id"] == "P-1E0D6A4D66"
            for section in case["sections"]
            if section["section_id"] == "S003"
        ).get("title", ""),
        next(
            section
            for case in manifest["cases"]
            if case["presentation_id"] == "P-1E0D6A4D66"
            for section in case["sections"]
            if section["section_id"] == "S003"
        ).get("text", ""),
    )
    numeric_entry = entries[numeric_hash]
    numeric_replacements = 0
    for field in ("title_zh", "text_zh"):
        numeric_replacements += numeric_entry[field].count("百分之二十")
        numeric_replacements += numeric_entry[field].count("百分之十五")
        numeric_entry[field] = numeric_entry[field].replace("百分之二十", "20%")
        numeric_entry[field] = numeric_entry[field].replace("百分之十五", "15%")
    if numeric_replacements:
        counts["数字格式：百分之二十/十五 -> 20%/15%"] += numeric_replacements

    normalized["normalization_version"] = NORMALIZATION_VERSION
    normalized["normalized_at"] = datetime.now(timezone.utc).isoformat()
    audit = {
        "schema_version": "annotation_translation_normalization_audit.v1",
        "normalization_version": NORMALIZATION_VERSION,
        "normalized_at": normalized["normalized_at"],
        "replacements": dict(sorted(counts.items())),
        "total_replacements": sum(counts.values()),
    }
    return normalized, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=FRONTEND / "data/manifest.json")
    parser.add_argument(
        "--cache", type=Path, default=FRONTEND / "data/translation_cache_zh.json"
    )
    parser.add_argument(
        "--output", type=Path, default=FRONTEND / "data/translations_zh.json"
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=FRONTEND.parent / "internal/translation_normalization_audit.json",
    )
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    cache = load_json(args.cache)
    normalized, audit = normalize(manifest, cache)
    if args.audit.exists():
        previous = load_json(args.audit)
        if previous.get("normalization_version") == NORMALIZATION_VERSION:
            merged = Counter(previous.get("replacements") or {})
            merged.update(audit["replacements"])
            audit["replacements"] = dict(sorted(merged.items()))
            audit["total_replacements"] = sum(merged.values())
    output = build_output(manifest, normalized, str(normalized["model"]))
    write_json(args.cache, normalized)
    write_json(args.output, output)
    write_json(args.audit, audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
