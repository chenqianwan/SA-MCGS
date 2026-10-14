#!/usr/bin/env python3
"""Translate the expert presentation into Chinese with a resumable cache."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[5]
FRONTEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

from src.llm.openai_client import OpenAIClient


DEFAULT_MANIFEST = FRONTEND / "data" / "manifest.json"
DEFAULT_CACHE = FRONTEND / "data" / "translation_cache_zh.json"
DEFAULT_OUTPUT = FRONTEND / "data" / "translations_zh.json"
DEFAULT_LOG = FRONTEND / "data" / "translation_calls.jsonl"
PROMPT_VERSION = "expert_material_legal_zh_v1"


class TranslationError(RuntimeError):
    pass


def canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def source_hash(title: str, text: str) -> str:
    return canonical_hash({"title": title, "text": text})


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_cache(path: Path, model: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": "annotation_translation_cache.zh-CN.v1",
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "entries": {},
        }
    cache = load_json(path)
    if cache.get("prompt_version") != PROMPT_VERSION or cache.get("model") != model:
        raise TranslationError(
            "translation cache belongs to a different prompt/model; use a new cache path"
        )
    return cache


def unique_sources(manifest: dict[str, Any]) -> dict[str, dict[str, str]]:
    sources: dict[str, dict[str, str]] = {}
    for case in manifest["cases"]:
        for section in case["sections"]:
            title = str(section.get("title") or "")
            text = str(section.get("text") or "")
            digest = source_hash(title, text)
            current = {"title": title, "text": text}
            if digest in sources and sources[digest] != current:
                raise TranslationError(f"source hash collision: {digest}")
            sources[digest] = current
    return sources


def make_batches(
    items: list[tuple[str, dict[str, str]]], max_chars: int, max_items: int
) -> list[list[tuple[str, dict[str, str]]]]:
    batches: list[list[tuple[str, dict[str, str]]]] = []
    current: list[tuple[str, dict[str, str]]] = []
    current_chars = 0
    for item in items:
        item_chars = len(item[1]["title"]) + len(item[1]["text"])
        if current and (
            len(current) >= max_items or current_chars + item_chars > max_chars
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(item)
        current_chars += item_chars
    if current:
        batches.append(current)
    return batches


def prompt_for(batch: list[tuple[str, dict[str, str]]]) -> str:
    items = [
        {"id": digest, "title": source["title"], "text": source["text"]}
        for digest, source in batch
    ]
    return (
        "请把下面的法律、合同、公司披露材料准确翻译成简体中文。返回严格 JSON 对象，"
        "格式为 {\"translations\":[{\"id\":...,\"title_zh\":...,\"text_zh\":...}]}。\n"
        "要求：\n"
        "1. 每个 id 必须原样返回一次，不得增加、遗漏或合并条目。\n"
        "2. 忠实直译，不润色，不补充解释，不消解原文中的冲突或歧义。\n"
        "3. 完整保留数字、金额、百分比、日期、条号、交叉引用、否定、例外和条件。\n"
        "4. 公司名、人名、地址、法条编号和缩写可保留原文；字段名和叙述性文字翻译成中文。\n"
        "5. 全大写 defined terms 应在同一批内保持译法一致。\n"
        "6. 原字段中的换行结构尽量保留。\n\n"
        + json.dumps({"items": items}, ensure_ascii=False)
    )


def validate_response(
    response: Any, batch: list[tuple[str, dict[str, str]]]
) -> dict[str, dict[str, str]]:
    translations = response.get("translations") if isinstance(response, dict) else None
    if not isinstance(translations, list):
        raise TranslationError("response has no translations list")
    expected = {digest for digest, _ in batch}
    parsed: dict[str, dict[str, str]] = {}
    for row in translations:
        if not isinstance(row, dict):
            raise TranslationError("translation row is not an object")
        digest = str(row.get("id") or "")
        title_zh = row.get("title_zh")
        text_zh = row.get("text_zh")
        if digest in parsed or digest not in expected:
            raise TranslationError(f"unexpected or duplicate translation id: {digest}")
        if not isinstance(title_zh, str) or not isinstance(text_zh, str):
            raise TranslationError(f"translation fields are not strings: {digest}")
        source = dict(batch)[digest]
        if source["title"] and not title_zh.strip():
            raise TranslationError(f"missing title translation: {digest}")
        if source["text"] and not text_zh.strip():
            raise TranslationError(f"missing text translation: {digest}")
        parsed[digest] = {"title_zh": title_zh, "text_zh": text_zh}
    if set(parsed) != expected:
        raise TranslationError(
            f"translation id mismatch: missing={sorted(expected - set(parsed))}"
        )
    return parsed


async def translate_batch(
    client: OpenAIClient,
    batch: list[tuple[str, dict[str, str]]],
    *,
    retries: int,
    max_tokens: int,
) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            response = await client.call_json(
                prompt_for(batch),
                temperature=0.0,
                max_tokens=max_tokens,
                system_prompt=(
                    "你是严谨的法律与法规翻译员。只输出要求的 JSON，不给解释。"
                ),
                retries=0,
            )
            parsed = validate_response(response, batch)
            return parsed, {
                "attempt": attempt,
                "items": len(batch),
                "source_chars": sum(
                    len(source["title"]) + len(source["text"])
                    for _, source in batch
                ),
                "usage": dict(client.last_usage),
            }
        except Exception as exc:  # keep exact failure in local log
            last_error = exc
            if attempt <= retries:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
    raise TranslationError(f"batch failed after retries: {last_error}")


def append_log(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_output(
    manifest: dict[str, Any], cache: dict[str, Any], model: str
) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for case in manifest["cases"]:
        sections: dict[str, Any] = {}
        for section in case["sections"]:
            title = str(section.get("title") or "")
            text = str(section.get("text") or "")
            digest = source_hash(title, text)
            translated = cache["entries"].get(digest)
            if not translated:
                raise TranslationError(f"cache is missing source: {digest}")
            sections[str(section["section_id"])] = {
                "source_hash": digest,
                "title_zh": translated["title_zh"],
                "text_zh": translated["text_zh"],
            }
        cases[str(case["presentation_id"])] = {"sections": sections}
    payload = {
        "schema_version": "annotation_translation.zh-CN.v1",
        "locale": "zh-CN",
        "source_manifest_hash": manifest["manifest_hash"],
        "translation_model": model,
        "prompt_version": PROMPT_VERSION,
        "normalization_version": cache.get("normalization_version"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cases": cases,
    }
    payload["translation_pack_hash"] = canonical_hash(payload)
    return payload


async def run(args: argparse.Namespace) -> None:
    manifest = load_json(args.manifest)
    cache = load_cache(args.cache, args.model)
    sources = unique_sources(manifest)
    pending = sorted(
        (digest, source)
        for digest, source in sources.items()
        if digest not in cache["entries"]
    )
    batches = make_batches(pending, args.max_source_chars, args.max_items)
    print(
        json.dumps(
            {
                "unique_sources": len(sources),
                "cached": len(sources) - len(pending),
                "pending": len(pending),
                "batches": len(batches),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if pending and not os.environ.get(args.api_key_env):
        raise TranslationError(f"missing API key environment: {args.api_key_env}")
    client = OpenAIClient(
        {
            "provider": "openai",
            "model": args.model,
            "base_url": args.base_url,
            "api_key_env": args.api_key_env,
            "timeout": args.timeout,
            "max_retries": 0,
        }
    )
    try:
        for index, batch in enumerate(batches, start=1):
            translated, audit = await translate_batch(
                client,
                batch,
                retries=args.retries,
                max_tokens=args.max_tokens,
            )
            for digest, value in translated.items():
                cache["entries"][digest] = {
                    **value,
                    "source_title_sha256": canonical_hash(
                        dict(batch)[digest]["title"]
                    ),
                    "source_text_sha256": canonical_hash(dict(batch)[digest]["text"]),
                }
            cache["updated_at"] = datetime.now(timezone.utc).isoformat()
            write_json(args.cache, cache)
            append_log(
                args.log,
                {
                    "recorded_at": cache["updated_at"],
                    "batch": index,
                    "batches": len(batches),
                    "model": args.model,
                    **audit,
                },
            )
            print(
                json.dumps(
                    {
                        "batch": index,
                        "batches": len(batches),
                        "translated": len(translated),
                        "cache_entries": len(cache["entries"]),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    finally:
        await client.close()
    output = build_output(manifest, cache, args.model)
    write_json(args.output, output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "presentations": len(output["cases"]),
                "sections": sum(
                    len(case["sections"]) for case in output["cases"].values()
                ),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--model", default="gemini-2.5-pro")
    parser.add_argument("--base-url", default="https://api3.xhub.chat/v1")
    parser.add_argument("--api-key-env", default="XHUB_API_KEY")
    parser.add_argument("--max-source-chars", type=int, default=12000)
    parser.add_argument("--max-items", type=int, default=18)
    parser.add_argument("--max-tokens", type=int, default=20000)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
