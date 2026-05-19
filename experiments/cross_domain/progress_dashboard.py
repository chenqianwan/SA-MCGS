"""Tiny live dashboard for long-running cross-domain battle experiments.

The experiment runner writes checkpoint files after each completed method run.
This server reads the newest checkpoint on every request and renders a small
browser dashboard, so the long experiment does not need to be restarted or
wrapped with a separate logger.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _latest_file(pattern: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _load_json(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return [{"method": "dashboard_error", "error": f"Failed to read checkpoint: {exc}"}]


def _load_json_obj(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        return {"summary": {"dashboard_error": 1}, "error": f"Failed to read status: {exc}"}


def _load_records_from_status(status: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for task in status.get("tasks", []):
        result_file = task.get("result_file")
        path = Path(result_file) if result_file else None
        if not path or not path.exists():
            run_tag = task.get("run_tag")
            path = _latest_file(f"*{run_tag}*.partial.json") if run_tag else None
        if not path or not path.exists():
            continue
        data = _load_json(path)
        if isinstance(data, list):
            for record in data:
                if isinstance(record, dict):
                    enriched = dict(record)
                    enriched["_task_template"] = task.get("template")
                    enriched["_task_severity"] = task.get("severity")
                    enriched["_task_size"] = task.get("size")
                    enriched["_task_compression_profile"] = task.get("compression_profile")
                    records.append(enriched)
    return records


def _truthy(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False
    return None


def _fmt_rate(num: int, den: int) -> str:
    if den <= 0:
        return "-"
    return f"{num}/{den} ({num / den:.0%})"


def _as_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.0%}"
    except Exception:
        return "-"


def _record_case_key(record: dict[str, Any]) -> str:
    return "|".join(
        str(record.get(k, ""))
        for k in (
            "domain",
            "scc_id",
            "model",
            "scc_size",
            "_task_template",
            "_task_severity",
            "_task_compression_profile",
        )
    )


def _metric_values(record: dict[str, Any]) -> dict[str, Any]:
    method = record.get("method")
    if method == "naive":
        risk_any = _truthy(record.get("direct_contains_any_risk_node"))
        risk_all = _truthy(record.get("direct_contains_all_risk_nodes"))
        compression = record.get("direct_compression_ratio")
        subgraph_size = record.get("direct_risk_subgraph_size")
    elif method == "sa-mcgs":
        risk_any = _truthy(
            record.get("core_evidence_contains_any_risk_node")
            if "core_evidence_contains_any_risk_node" in record
            else record.get("contains_any_risk_node")
        )
        risk_all = _truthy(
            record.get("core_evidence_contains_all_risk_nodes")
            if "core_evidence_contains_all_risk_nodes" in record
            else record.get("contains_all_risk_nodes")
        )
        compression = (
            record.get("core_evidence_compression_ratio")
            if "core_evidence_compression_ratio" in record
            else record.get("compression_ratio")
        )
        subgraph_size = (
            record.get("core_evidence_risk_subgraph_size")
            if "core_evidence_risk_subgraph_size" in record
            else record.get("risk_subgraph_size")
        )
    else:
        risk_any = risk_all = compression = subgraph_size = None

    return {
        "root_top3": _truthy(record.get("top3_hit")),
        "risk_any": risk_any,
        "risk_all": risk_all,
        "compression": compression,
        "subgraph_size": subgraph_size,
        "oc_count": record.get("oc_count"),
        "critical_locked": len(record.get("critical_pair_locked_edges") or []),
        "critical_candidate": len(record.get("critical_pair_candidate_edges") or []),
        "critical_revisits": len(record.get("critical_pair_revisit_history") or []),
        "effective_oc": _truthy(record.get("effective_oc_hit"))
        if "effective_oc_hit" in record
        else _truthy(record.get("core_evidence_contains_any_risk_node")),
    }


def _pair_key(record: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(record.get("domain", "")),
        str(record.get("scc_id", "")),
        str(record.get("model", "")),
        str(record.get("scc_size", "")),
        str(record.get("_task_template") or record.get("injected_conflict_family") or ""),
        str(record.get("_task_severity") or record.get("injected_conflict_severity") or ""),
    )


def _bool_mark(value: bool | None) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "-"


def _cmp_bool(a: bool | None, b: bool | None) -> tuple[str, str]:
    if a is True and b is not True:
        return "win", "lose"
    if b is True and a is not True:
        return "lose", "win"
    if a is None or b is None:
        return "", ""
    return "tie", "tie"


def _cmp_float(a: Any, b: Any) -> tuple[str, str]:
    try:
        af = float(a)
        bf = float(b)
    except Exception:
        return "", ""
    if abs(af - bf) < 1e-9:
        return "tie", "tie"
    return ("win", "lose") if af > bf else ("lose", "win")


def _fmt_pair_bool(value: bool | None, method: str, status: str) -> dict[str, str]:
    return {
        "value": _bool_mark(value),
        "class": f"{method} {status}".strip(),
    }


def _fmt_pair_pct(value: Any, method: str, status: str) -> dict[str, str]:
    return {
        "value": _as_pct(value),
        "class": f"{method} {status}".strip(),
    }


def _build_pairwise_rows(completed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_case: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    latest_index: dict[tuple[str, str, str, str], int] = {}
    for idx, record in enumerate(completed, 1):
        method = record.get("method")
        if method not in {"naive", "sa-mcgs"}:
            continue
        key = _pair_key(record)
        by_case[key][str(method)] = record
        latest_index[key] = idx

    rows = []
    for key, methods in by_case.items():
        naive = methods.get("naive")
        sa = methods.get("sa-mcgs")
        if not naive or not sa:
            continue

        nm = _metric_values(naive)
        sm = _metric_values(sa)
        n_root, s_root = _cmp_bool(nm["root_top3"], sm["root_top3"])
        n_any, s_any = _cmp_bool(nm["risk_any"], sm["risk_any"])
        n_all, s_all = _cmp_bool(nm["risk_all"], sm["risk_all"])
        n_comp, s_comp = _cmp_float(nm["compression"], sm["compression"])
        domain, scc_id, model, size, template, severity = key
        rows.append(
            {
                "order": latest_index.get(key, 0),
                "domain": domain,
                "size": size,
                "model": model,
                "scc": scc_id,
                "template": template,
                "severity": severity,
                "root_naive": _fmt_pair_bool(nm["root_top3"], "naive", n_root),
                "root_sa": _fmt_pair_bool(sm["root_top3"], "sa", s_root),
                "any_naive": _fmt_pair_bool(nm["risk_any"], "naive", n_any),
                "any_sa": _fmt_pair_bool(sm["risk_any"], "sa", s_any),
                "all_naive": _fmt_pair_bool(nm["risk_all"], "naive", n_all),
                "all_sa": _fmt_pair_bool(sm["risk_all"], "sa", s_all),
                "comp_naive": _fmt_pair_pct(nm["compression"], "naive", n_comp),
                "comp_sa": _fmt_pair_pct(sm["compression"], "sa", s_comp),
                "naive_subgraph": (
                    f"{nm['subgraph_size']}/{naive.get('scc_size')}"
                    if nm["subgraph_size"] is not None
                    else "-"
                ),
                "sa_subgraph": (
                    f"{sm['subgraph_size']}/{sa.get('scc_size')}"
                    if sm["subgraph_size"] is not None
                    else "-"
                ),
                "oc": sa.get("oc_count", "-"),
                "naive_error": naive.get("error"),
                "sa_error": sa.get("error"),
            }
        )
    rows.sort(key=lambda r: r["order"], reverse=True)
    return rows


def _build_metric_rows(
    completed: list[dict[str, Any]],
    label_fn,
    sort_fn=None,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in completed:
        label = str(label_fn(record) or "?")
        method = str(record.get("method", "?"))
        key = (label, method)
        stats = groups.setdefault(
            key,
            {
                "label": label,
                "method": method,
                "count": 0,
                "root_top3": 0,
                "risk_any": 0,
                "risk_all": 0,
                "errors": 0,
                "subgraph_sum": 0.0,
                "subgraph_n": 0,
                "compression_sum": 0.0,
                "compression_n": 0,
                "effective_compression_sum": 0.0,
                "effective_compression_n": 0,
                "oc_hit": 0,
                "effective_oc_hit": 0,
            },
        )
        stats["count"] += 1
        metrics = _metric_values(record)
        if record.get("error"):
            stats["errors"] += 1
        if metrics["root_top3"] is True:
            stats["root_top3"] += 1
        if metrics["risk_any"] is True:
            stats["risk_any"] += 1
        if metrics["risk_all"] is True:
            stats["risk_all"] += 1
        if metrics["subgraph_size"] is not None:
            try:
                stats["subgraph_sum"] += float(metrics["subgraph_size"])
                stats["subgraph_n"] += 1
            except Exception:
                pass
        if metrics["compression"] is not None:
            try:
                compression_value = float(metrics["compression"])
                stats["compression_sum"] += compression_value
                stats["compression_n"] += 1
                if metrics["risk_any"] is True:
                    stats["effective_compression_sum"] += compression_value
                    stats["effective_compression_n"] += 1
            except Exception:
                pass
        if method == "sa-mcgs" and int(record.get("oc_count") or 0) > 0:
            stats["oc_hit"] += 1
        if method == "sa-mcgs" and metrics["effective_oc"] is True:
            stats["effective_oc_hit"] += 1

    rows = []
    for stats in groups.values():
        den = stats["count"]
        rows.append(
            {
                "label": stats["label"],
                "method": stats["method"],
                "count": den,
                "valid": max(0, den - stats["errors"]),
                "errors": stats["errors"],
                "root_top3": _fmt_rate(stats["root_top3"], den),
                "risk_any": _fmt_rate(stats["risk_any"], den),
                "risk_all": _fmt_rate(stats["risk_all"], den),
                "avg_subgraph": (
                    f"{stats['subgraph_sum'] / stats['subgraph_n']:.1f}"
                    if stats["subgraph_n"]
                    else "-"
                ),
                "avg_compression": (
                    f"{stats['compression_sum'] / stats['compression_n']:.0%}"
                    if stats["compression_n"]
                    else "-"
                ),
                "effective_compression": (
                    f"{stats['effective_compression_sum'] / stats['effective_compression_n']:.0%}"
                    if stats["effective_compression_n"]
                    else "-"
                ),
                "oc_hit": _fmt_rate(stats["oc_hit"], den) if stats["method"] == "sa-mcgs" else "-",
                "effective_oc_hit": (
                    _fmt_rate(stats["effective_oc_hit"], den)
                    if stats["method"] == "sa-mcgs"
                    else "-"
                ),
            }
        )
    rows.sort(key=sort_fn or (lambda r: (r["label"], r["method"])))
    return rows


def _avg_numeric(values: list[Any]) -> float | None:
    nums: list[float] = []
    for value in values:
        if isinstance(value, bool):
            nums.append(1.0 if value else 0.0)
            continue
        try:
            nums.append(float(value))
        except Exception:
            pass
    if not nums:
        return None
    return sum(nums) / len(nums)


def _build_convergence_summary(completed: list[dict[str, Any]]) -> dict[str, Any]:
    sa_records = [
        r for r in completed
        if r.get("method") == "sa-mcgs" and isinstance(r.get("convergence_trace"), list)
    ]

    def aggregate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_rollout: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            for point in record.get("convergence_trace") or []:
                if not isinstance(point, dict):
                    continue
                try:
                    rollout = int(point.get("rollout") or 0)
                except Exception:
                    continue
                if rollout > 0:
                    by_rollout[rollout].append(point)

        series: list[dict[str, Any]] = []
        for rollout in sorted(by_rollout):
            points = by_rollout[rollout]

            def bool_rate(key: str) -> float | None:
                values = [_truthy(p.get(key)) for p in points]
                values = [v for v in values if v is not None]
                if not values:
                    return None
                return sum(1 for v in values if v) / len(values)

            def avg(key: str) -> float | None:
                return _avg_numeric([p.get(key) for p in points])

            series.append(
                {
                    "rollout": rollout,
                    "n": len(points),
                    "risk_any_rate": bool_rate("risk_any"),
                    "risk_all_rate": bool_rate("risk_all"),
                    "effective_oc_rate": bool_rate("effective_oc"),
                    "risk_coverage": avg("risk_coverage"),
                    "valuable_coverage": avg("valuable_coverage"),
                    "compression": avg("compression_ratio"),
                    "subgraph_size": avg("subgraph_size"),
                }
            )
        return series

    by_domain_size: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    case_rows: list[dict[str, Any]] = []
    for record in sa_records:
        domain = str(record.get("domain", "?"))
        size = str(record.get("scc_size") or record.get("_task_size") or "?")
        by_domain[domain].append(record)
        by_domain_size[f"{domain}:{size}"].append(record)

        trace = record.get("convergence_trace") or []

        def first_rollout(key: str) -> int | None:
            for point in trace:
                if _truthy(point.get(key)) is True:
                    try:
                        return int(point.get("rollout") or 0)
                    except Exception:
                        return None
            return None

        final = trace[-1] if trace else {}
        case_rows.append(
            {
                "domain": domain,
                "size": size,
                "model": record.get("model"),
                "template": record.get("_task_template") or record.get("injected_conflict_family"),
                "first_any": first_rollout("risk_any"),
                "first_all": first_rollout("risk_all"),
                "first_effective_oc": first_rollout("effective_oc"),
                "final_risk_coverage": final.get("risk_coverage"),
                "final_risk_all": _truthy(final.get("risk_all")),
                "final_compression": final.get("compression_ratio"),
                "final_subgraph_size": final.get("subgraph_size"),
                "locked": len(record.get("critical_pair_locked_edges") or []),
                "revisits": len(record.get("critical_pair_revisit_history") or []),
            }
        )

    def group_sort_key(label: str) -> tuple[str, int]:
        domain, _, size = label.partition(":")
        try:
            size_i = int(size)
        except Exception:
            size_i = 9999
        return domain, size_i

    return {
        "overall": aggregate(sa_records),
        "by_domain": {k: aggregate(v) for k, v in sorted(by_domain.items())},
        "by_domain_size": {
            k: aggregate(v)
            for k, v in sorted(by_domain_size.items(), key=lambda kv: group_sort_key(kv[0]))
        },
        "cases": sorted(
            case_rows,
            key=lambda r: (
                str(r["domain"]),
                int(r["size"]) if str(r["size"]).isdigit() else 9999,
                str(r.get("template") or ""),
                str(r.get("model") or ""),
            ),
        ),
    }


def _summarize(records: list[dict[str, Any]], expected_total: int) -> dict[str, Any]:
    completed = [
        r for r in records
        if r.get("method") in {"naive", "sa-mcgs"}
    ]
    errors = [r for r in completed if r.get("error")]

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for record in completed:
        key = (str(record.get("domain", "?")), str(record.get("method", "?")))
        stats = groups.setdefault(
            key,
            {
                "domain": key[0],
                "method": key[1],
                "count": 0,
                "root_top3": 0,
                "risk_any": 0,
                "risk_all": 0,
                "errors": 0,
                "subgraph_sum": 0.0,
                "subgraph_n": 0,
                "compression_sum": 0.0,
                "compression_n": 0,
                "oc_hit": 0,
                "effective_oc_hit": 0,
            },
        )
        stats["count"] += 1
        metrics = _metric_values(record)
        if record.get("error"):
            stats["errors"] += 1
        if metrics["root_top3"] is True:
            stats["root_top3"] += 1
        if metrics["risk_any"] is True:
            stats["risk_any"] += 1
        if metrics["risk_all"] is True:
            stats["risk_all"] += 1
        if metrics["subgraph_size"] is not None:
            try:
                stats["subgraph_sum"] += float(metrics["subgraph_size"])
                stats["subgraph_n"] += 1
            except Exception:
                pass
        if metrics["compression"] is not None:
            try:
                stats["compression_sum"] += float(metrics["compression"])
                stats["compression_n"] += 1
            except Exception:
                pass
        if record.get("method") == "sa-mcgs" and int(record.get("oc_count") or 0) > 0:
            stats["oc_hit"] += 1
        if record.get("method") == "sa-mcgs" and metrics["effective_oc"] is True:
            stats["effective_oc_hit"] += 1

    group_rows = []
    for stats in sorted(groups.values(), key=lambda x: (x["domain"], x["method"])):
        den = stats["count"]
        valid = max(0, den - stats["errors"])
        group_rows.append(
            {
                "domain": stats["domain"],
                "method": stats["method"],
                "count": den,
                "valid": valid,
                "errors": stats["errors"],
                "root_top3": _fmt_rate(stats["root_top3"], den),
                "risk_any": _fmt_rate(stats["risk_any"], den),
                "risk_all": _fmt_rate(stats["risk_all"], den),
                "avg_subgraph": (
                    f"{stats['subgraph_sum'] / stats['subgraph_n']:.1f}"
                    if stats["subgraph_n"]
                    else "-"
                ),
                "avg_compression": (
                    f"{stats['compression_sum'] / stats['compression_n']:.0%}"
                    if stats["compression_n"]
                    else "-"
                ),
                "oc_hit": _fmt_rate(stats["oc_hit"], den) if stats["method"] == "sa-mcgs" else "-",
                "effective_oc_hit": (
                    _fmt_rate(stats["effective_oc_hit"], den)
                    if stats["method"] == "sa-mcgs"
                    else "-"
                ),
            }
        )

    by_domain = defaultdict(int)
    by_method = defaultdict(int)
    sizes = defaultdict(int)
    for record in completed:
        by_domain[str(record.get("domain", "?"))] += 1
        by_method[str(record.get("method", "?"))] += 1
        sizes[str(record.get("scc_size", "?"))] += 1

    recent = []
    for display_idx, record in enumerate(completed[::-1], 1):
        metrics = _metric_values(record)
        recent.append(
            {
                "idx": len(completed) - display_idx + 1,
                "domain": record.get("domain"),
                "size": record.get("scc_size"),
                "model": record.get("model"),
                "method": record.get("method"),
                "profile": (
                    record.get("_task_compression_profile")
                    or record.get("mcgs_compression_profile")
                    or "current"
                ),
                "top3": metrics["root_top3"],
                "risk_any": metrics["risk_any"],
                "risk_all": metrics["risk_all"],
                "compression": _as_pct(metrics["compression"]),
                "subgraph": (
                    f"{metrics['subgraph_size']}/{record.get('scc_size')}"
                    if metrics["subgraph_size"] is not None
                    else "-"
                ),
                "oc": record.get("oc_count", "-"),
                "critical_locked": metrics["critical_locked"],
                "critical_revisits": metrics["critical_revisits"],
                "error": record.get("error"),
            }
        )

    matched_cases = len({_record_case_key(r) for r in completed})
    return {
        "expected_total": expected_total,
        "completed_total": len(completed),
        "completed_ratio": (len(completed) / expected_total if expected_total else 0),
        "matched_cases": matched_cases,
        "error_total": len(errors),
        "by_domain": dict(sorted(by_domain.items())),
        "by_method": dict(sorted(by_method.items())),
        "sizes": dict(sorted(sizes.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 9999)),
        "groups": group_rows,
        "severity_groups": _build_metric_rows(
            completed,
            lambda r: r.get("_task_severity") or r.get("injected_conflict_severity"),
            sort_fn=lambda r: (
                {"standard": 0, "severe": 1, "critical": 2}.get(r["label"], 99),
                r["method"],
            ),
        ),
        "template_groups": _build_metric_rows(
            completed,
            lambda r: r.get("_task_template") or r.get("injected_conflict_family"),
        ),
        "profile_groups": _build_metric_rows(
            completed,
            lambda r: (
                r.get("_task_compression_profile")
                or r.get("mcgs_compression_profile")
                or "current"
            ),
            sort_fn=lambda r: (
                {"current": 0, "conservative": 1, "balanced": 2, "aggressive": 3}.get(
                    r["label"], 99
                ),
                r["method"],
            ),
        ),
        "size_groups": _build_metric_rows(
            completed,
            lambda r: f"{r.get('domain')}:{r.get('_task_size') or r.get('scc_size')}",
            sort_fn=lambda r: (
                r["label"].split(":", 1)[0],
                int(r["label"].split(":", 1)[1]) if ":" in r["label"] and r["label"].split(":", 1)[1].isdigit() else 9999,
                r["method"],
            ),
        ),
        "pairwise": _build_pairwise_rows(completed),
        "convergence": _build_convergence_summary(completed),
        "recent": recent,
    }


def _process_info(match: str) -> dict[str, Any]:
    try:
        out = subprocess.check_output(
            ["ps", "-axo", "pid,etime,command"],
            text=True,
        )
    except Exception as exc:
        return {"running": False, "error": str(exc)}

    matches = []
    for line in out.splitlines()[1:]:
        if match in line and "progress_dashboard.py" not in line:
            parts = line.strip().split(None, 2)
            if len(parts) == 3:
                matches.append({"pid": parts[0], "elapsed": parts[1], "command": parts[2]})
    return {"running": bool(matches), "matches": matches[:3]}


def _payload(args: argparse.Namespace) -> dict[str, Any]:
    status_path = Path(args.status_file) if args.status_file else None
    status = _load_json_obj(status_path) if status_path else {}
    path = None if status else _latest_file(args.result_glob)
    records = _load_records_from_status(status) if status else _load_json(path)
    summary = _summarize(records, args.expected_total)
    tasks = status.get("tasks", []) if status else []
    task_summary = status.get("summary", {}) if status else {}
    return {
        "now": time.strftime("%Y-%m-%d %H:%M:%S"),
        "checkpoint": str(status_path if status else path) if (status_path or path) else None,
        "checkpoint_mtime": (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
            if path and path.exists()
            else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(status_path.stat().st_mtime))
            if status_path and status_path.exists()
            else None
        ),
        "checkpoint_size_mb": round((status_path if status else path).stat().st_size / 1024 / 1024, 2)
        if (status_path if status else path) and (status_path if status else path).exists()
        else None,
        "process": _process_info(args.process_match),
        "summary": summary,
        "task_summary": task_summary,
        "tasks": tasks,
    }


def _html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Long-ring Experiment Progress</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101214;
      --panel: #181b1f;
      --panel2: #20242a;
      --text: #f1f5f9;
      --muted: #9aa4b2;
      --line: #303641;
      --blue: #4f8cff;
      --green: #18a978;
      --orange: #f28c28;
      --red: #ef4444;
      --purple: #a855f7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { max-width: 1380px; margin: 0 auto; padding: 28px; }
    header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 18px; }
    h1 { margin: 0; font-size: 30px; letter-spacing: 0; }
    .sub { color: var(--muted); margin-top: 6px; }
    .pill {
      display: inline-flex; align-items: center; gap: 8px;
      border: 1px solid var(--line); background: var(--panel2);
      padding: 7px 10px; border-radius: 999px; color: var(--muted);
      white-space: nowrap;
      text-decoration: none;
    }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--red); }
    .dot.on { background: var(--green); box-shadow: 0 0 14px rgba(24,169,120,.65); }
    .header-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .card {
      background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
      padding: 16px; min-width: 0;
    }
    .label { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
    .value { font-size: 30px; font-weight: 800; }
    .value small { font-size: 16px; color: var(--muted); font-weight: 600; }
    .progress { height: 14px; background: #0b0d10; border-radius: 999px; overflow: hidden; border: 1px solid var(--line); margin-top: 12px; }
    .bar { height: 100%; background: linear-gradient(90deg, var(--blue), var(--green)); width: 0%; transition: width .3s ease; }
    section { margin-top: 18px; }
    h2 { font-size: 20px; margin: 0 0 12px; }
    table { width: 100%; border-collapse: collapse; overflow: hidden; }
    th, td { padding: 10px 11px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: #dbeafe; font-weight: 750; background: #141820; position: sticky; top: 0; }
    tr:last-child td { border-bottom: 0; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .ok { color: var(--green); font-weight: 750; }
    .bad { color: var(--red); font-weight: 750; }
    .warn { color: var(--orange); font-weight: 750; }
    .muted { color: var(--muted); }
    .split { display: grid; grid-template-columns: 1.25fr .75fr; gap: 14px; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; }
    .chip { padding: 6px 9px; background: var(--panel2); border: 1px solid var(--line); border-radius: 7px; }
    .table-scroll {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #141820;
    }
    .table-scroll table { min-width: 1120px; }
    .metrics-table table { min-width: 1320px; }
    .all-items { max-height: 68vh; }
    .task-items { max-height: 52vh; }
    .method-naive td { background: rgba(239, 68, 68, .035); }
    .method-sa-mcgs td { background: rgba(24, 169, 120, .035); }
    .status-running { color: var(--blue); font-weight: 800; }
    .status-done { color: var(--green); font-weight: 800; }
    .status-failed { color: var(--red); font-weight: 800; }
    .status-pending { color: var(--muted); font-weight: 700; }
    .figure-stack { display: grid; gap: 18px; }
    .figure-card {
      background: #f8fafc;
      border-radius: 8px;
      padding: 10px;
      border: 1px solid var(--line);
    }
    .figure-card img {
      display: block;
      width: 100%;
      height: auto;
      border-radius: 4px;
    }
    pre { white-space: pre-wrap; word-break: break-word; margin: 0; color: var(--muted); max-height: 135px; overflow: auto; }
    @media (max-width: 980px) {
      main { padding: 18px; }
      header, .split { display: block; }
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .pill { margin-top: 12px; }
    }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Long-ring Experiment Progress</h1>
      <div class="sub">CUAD 12-26 · Wikipedia 34 · BGB 11-25 · rollout=60 · auto refresh 5s</div>
    </div>
    <div class="header-actions">
      <a class="pill" href="/analysis" target="_blank">Open analysis report</a>
      <div class="pill"><span id="runDot" class="dot"></span><span id="runText">checking...</span></div>
    </div>
  </header>

  <div class="grid">
    <div class="card">
      <div class="label">Completed Records</div>
      <div class="value"><span id="completed">-</span> <small id="expected">/ -</small></div>
      <div class="progress"><div id="bar" class="bar"></div></div>
    </div>
    <div class="card">
      <div class="label">Matched SCC×Model Cases</div>
      <div class="value" id="matched">-</div>
    </div>
    <div class="card">
      <div class="label">Errors</div>
      <div class="value" id="errors">-</div>
    </div>
  </div>

  <section class="card">
    <h2>Severity Grid Tasks</h2>
    <div class="sub">Each row is one domain × size × template × severity block. The table scrolls.</div>
    <div id="taskChips" class="chips" style="margin: 10px 0 12px"></div>
    <div class="table-scroll task-items">
    <table>
      <thead><tr><th>#</th><th>Status</th><th>Domain</th><th>Size</th><th>Template</th><th>Severity</th><th>Attempt</th><th>Elapsed</th><th>Result</th><th>Log</th></tr></thead>
      <tbody id="tasks"></tbody>
    </table>
    </div>
  </section>

  <section class="card">
    <h2>Severity Grid Analysis Charts</h2>
    <div class="sub">Final analysis from the completed 192 method records. Images are large and scroll normally.</div>
    <div class="figure-stack">
      <div class="figure-card"><img src="/figures/severitygrid_domain_size_metrics.png" alt="Method comparison by actual SCC size"></div>
      <div class="figure-card"><img src="/figures/severitygrid_severity_effect.png" alt="Severity effect"></div>
      <div class="figure-card"><img src="/figures/severitygrid_template_effect.png" alt="Template effect"></div>
      <div class="figure-card"><img src="/figures/severitygrid_compression_subgraph.png" alt="Compression and subgraph size"></div>
      <div class="figure-card"><img src="/figures/severitygrid_model_error_effect.png" alt="Model and error effect"></div>
      <div class="figure-card"><img src="/figures/severitygrid_sa_oc_vs_retention.png" alt="SA OC and retention"></div>
    </div>
  </section>

  <section class="card">
      <h2>Metrics So Far</h2>
      <div class="sub">Includes partial results from running blocks. N counts method records; Valid excludes parser/ranking errors.</div>
      <div class="table-scroll metrics-table">
      <table>
        <thead><tr><th>Domain</th><th>Method</th><th>N</th><th>Valid</th><th>Errors</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Avg subgraph</th><th>Compression</th><th>OC hit</th><th>Effective OC</th></tr></thead>
        <tbody id="groups"></tbody>
      </table>
      </div>
  </section>

  <section class="card">
      <h2>By Severity</h2>
      <div class="table-scroll metrics-table">
      <table>
        <thead><tr><th>Severity</th><th>Method</th><th>N</th><th>Valid</th><th>Errors</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Avg subgraph</th><th>Compression</th><th>OC hit</th><th>Effective OC</th></tr></thead>
        <tbody id="severityGroups"></tbody>
      </table>
      </div>
  </section>

  <section class="card">
      <h2>By Template</h2>
      <div class="table-scroll metrics-table">
      <table>
        <thead><tr><th>Template</th><th>Method</th><th>N</th><th>Valid</th><th>Errors</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Avg subgraph</th><th>Compression</th><th>OC hit</th><th>Effective OC</th></tr></thead>
        <tbody id="templateGroups"></tbody>
      </table>
      </div>
  </section>

  <section class="card">
      <h2>By Domain × Size</h2>
      <div class="table-scroll metrics-table">
      <table>
        <thead><tr><th>Domain:size</th><th>Method</th><th>N</th><th>Valid</th><th>Errors</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Avg subgraph</th><th>Compression</th><th>OC hit</th><th>Effective OC</th></tr></thead>
        <tbody id="sizeGroups"></tbody>
      </table>
      </div>
  </section>

  <section class="card">
      <h2>Distribution</h2>
      <div class="label">By domain</div><div id="byDomain" class="chips"></div>
      <div class="label" style="margin-top:14px">By method</div><div id="byMethod" class="chips"></div>
      <div class="label" style="margin-top:14px">SCC sizes completed</div><div id="sizes" class="chips"></div>
  </section>

  <section class="card">
    <h2>SA-MCGS Domain Convergence Lines</h2>
    <div class="sub">Rollout 1-60. These are generated from the final result JSON and served directly by this page.</div>
    <div class="figure-stack">
      <div class="figure-card"><img src="/figures/sa_domain_metric_lines.png" alt="SA domain metric lines"></div>
      <div class="figure-card"><img src="/figures/sa_domain_individual_risk_coverage.png" alt="SA individual risk coverage"></div>
      <div class="figure-card"><img src="/figures/sa_domain_risk_all_lines.png" alt="SA risk-all lines"></div>
    </div>
  </section>

  <section class="card">
    <h2>All Completed Items</h2>
    <div class="sub">Newest first. This table scrolls vertically and horizontally.</div>
    <div class="table-scroll all-items">
    <table>
      <thead><tr><th>#</th><th>Domain</th><th>Size</th><th>Model</th><th>Method</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Subgraph</th><th>Compression</th><th>OC</th><th>Critical locked</th><th>Revisits</th></tr></thead>
      <tbody id="recent"></tbody>
    </table>
    </div>
  </section>

  <section class="card">
    <h2>Process</h2>
    <pre id="process">-</pre>
  </section>
</main>
<script>
function yesNo(v) {
  if (v === true) return '<span class="ok">Yes</span>';
  if (v === false) return '<span class="bad">No</span>';
  return '<span class="muted">-</span>';
}
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function chips(obj) {
  const entries = Object.entries(obj || {});
  if (!entries.length) return '<span class="muted">none yet</span>';
  return entries.map(([k,v]) => `<span class="chip"><span class="mono">${esc(k)}</span>: ${esc(v)}</span>`).join('');
}
function taskStatusClass(status) {
  if (status === 'done') return 'status-done';
  if (status === 'running' || status === 'retrying') return 'status-running';
  if (status === 'failed') return 'status-failed';
  return 'status-pending';
}
function elapsed(t) {
  if (!t) return '-';
  const end = Date.now() / 1000;
  let sec = Math.max(0, Math.round(end - Number(t)));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m ? `${m}m ${s}s` : `${s}s`;
}
function metricRows(rows, firstHeader) {
  return (rows || []).map(r => `
    <tr>
      <td>${esc(r.label ?? r.domain)}</td><td>${esc(r.method)}</td><td>${esc(r.count)}</td><td>${esc(r.valid)}</td><td>${esc(r.errors)}</td>
      <td>${esc(r.root_top3)}</td><td>${esc(r.risk_any)}</td><td>${esc(r.risk_all)}</td>
      <td>${esc(r.avg_subgraph)}</td><td>${esc(r.avg_compression)}</td><td>${esc(r.oc_hit)}</td><td>${esc(r.effective_oc_hit)}</td>
    </tr>`).join('') || `<tr><td colspan="12" class="muted">No ${esc(firstHeader)} data yet.</td></tr>`;
}
async function refresh() {
  const res = await fetch('/api/progress?ts=' + Date.now());
  const data = await res.json();
  const s = data.summary;
  document.getElementById('completed').textContent = s.completed_total;
  document.getElementById('expected').textContent = '/ ' + s.expected_total;
  document.getElementById('matched').textContent = s.matched_cases;
  document.getElementById('errors').textContent = s.error_total;
  document.getElementById('errors').className = s.error_total ? 'value bad' : 'value ok';
  document.getElementById('bar').style.width = Math.min(100, Math.round(s.completed_ratio * 100)) + '%';
  document.getElementById('runDot').className = 'dot ' + (data.process.running ? 'on' : '');
  document.getElementById('runText').textContent = data.process.running ? 'running' : 'not running';
  document.getElementById('byDomain').innerHTML = chips(s.by_domain);
  document.getElementById('byMethod').innerHTML = chips(s.by_method);
  document.getElementById('sizes').innerHTML = chips(s.sizes);
  document.getElementById('taskChips').innerHTML = chips(data.task_summary || {});
  const taskRows = (data.tasks || []).slice().sort((a, b) => {
    const order = {running: 0, retrying: 1, failed: 2, pending: 3, done: 4};
    const oa = order[a.status] ?? 9;
    const ob = order[b.status] ?? 9;
    if (oa !== ob) return oa - ob;
    return Number(a.task_id) - Number(b.task_id);
  });
  document.getElementById('tasks').innerHTML = taskRows.map(t => `
    <tr>
      <td class="mono">${esc(t.task_id)}</td>
      <td class="${taskStatusClass(t.status)}">${esc(t.status)}</td>
      <td>${esc(t.domain)}</td><td>${esc(t.size)}</td><td class="mono">${esc(t.template)}</td><td>${esc(t.severity)}</td>
      <td>${esc(t.attempt || '-')}</td><td>${esc(elapsed(t.started_at))}</td>
      <td class="mono">${t.result_file ? esc(t.result_file.split('/').pop()) : '-'}</td>
      <td class="mono">${t.log_path ? esc(t.log_path.split('/').pop()) : '-'}</td>
    </tr>`).join('') || '<tr><td colspan="10" class="muted">No task status file loaded.</td></tr>';
  document.getElementById('groups').innerHTML = metricRows((s.groups || []).map(r => ({...r, label: r.domain})), 'domain');
  document.getElementById('severityGroups').innerHTML = metricRows(s.severity_groups, 'severity');
  document.getElementById('templateGroups').innerHTML = metricRows(s.template_groups, 'template');
  document.getElementById('sizeGroups').innerHTML = metricRows(s.size_groups, 'size');
  document.getElementById('recent').innerHTML = (s.recent || []).map(r => `
    <tr class="method-${esc(r.method)}">
      <td class="mono">${esc(r.idx)}</td><td>${esc(r.domain)}</td><td>${esc(r.size)}</td><td>${esc(r.model)}</td><td>${esc(r.method)}</td>
      <td>${yesNo(r.top3)}</td><td>${yesNo(r.risk_any)}</td><td>${yesNo(r.risk_all)}</td>
      <td class="mono">${esc(r.subgraph)}</td><td>${esc(r.compression)}</td><td>${esc(r.oc)}</td>
      <td>${esc(r.critical_locked)}</td><td>${esc(r.critical_revisits)}</td>
    </tr>`).join('') || '<tr><td colspan="13" class="muted">No completed records yet.</td></tr>';
  document.getElementById('process').textContent = JSON.stringify(data.process, null, 2);
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


def _clean_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Critical Long-ring Results</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0e1116;
      --panel: #151a22;
      --panel2: #1b2230;
      --line: #2b3443;
      --text: #f4f7fb;
      --muted: #9aa6b8;
      --green: #12b981;
      --red: #ef4e4e;
      --blue: #5b8cff;
      --amber: #f3a43b;
      --purple: #9b6cff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at 20% -10%, rgba(91,140,255,.18), transparent 32%),
        radial-gradient(circle at 82% 8%, rgba(18,185,129,.12), transparent 30%),
        var(--bg);
      color: var(--text);
      font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { max-width: 1260px; margin: 0 auto; padding: 30px 24px 46px; }
    header { display: flex; justify-content: space-between; gap: 18px; align-items: flex-start; margin-bottom: 18px; }
    h1 { margin: 0; font-size: 32px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 21px; }
    h3 { margin: 0 0 8px; font-size: 16px; color: #d9e6ff; }
    .sub { color: var(--muted); margin-top: 6px; }
    .pill {
      display: inline-flex; align-items: center; gap: 8px;
      border: 1px solid var(--line); background: rgba(27,34,48,.84);
      padding: 7px 11px; border-radius: 999px; color: var(--muted);
      white-space: nowrap; text-decoration: none;
    }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--muted); }
    .dot.on { background: var(--green); box-shadow: 0 0 14px rgba(18,185,129,.7); }
    .dot.done { background: var(--blue); }
    .hero {
      display: grid;
      grid-template-columns: 1.25fr .75fr;
      gap: 14px;
      margin-bottom: 16px;
    }
    .claim, .card {
      background: rgba(21,26,34,.92);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 18px;
      box-shadow: 0 16px 48px rgba(0,0,0,.18);
    }
    .claim-title { font-size: 19px; font-weight: 800; margin-bottom: 10px; }
    .claim-text { font-size: 16px; color: #dce7f7; max-width: 78ch; }
    .claim-text strong { color: #ffffff; }
    .metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .metric-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 14px;
      min-height: 128px;
    }
    .metric-label { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
    .metric-value { font-size: 30px; font-weight: 850; line-height: 1.1; }
    .metric-note { color: var(--muted); margin-top: 7px; font-size: 13px; }
    .ok { color: var(--green); font-weight: 800; }
    .bad { color: var(--red); font-weight: 800; }
    .warn { color: var(--amber); font-weight: 800; }
    .blue { color: var(--blue); font-weight: 800; }
    .section-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
    .bar-row { display: grid; grid-template-columns: 105px 1fr 86px; gap: 10px; align-items: center; margin: 11px 0; }
    .track { height: 13px; background: #0c1017; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
    .fill { height: 100%; border-radius: 999px; width: 0; }
    .fill.naive { background: linear-gradient(90deg, #cf3f36, #ef6a5b); }
    .fill.sa { background: linear-gradient(90deg, #0f8f69, #16c994); }
    .fill.blue { background: linear-gradient(90deg, #3b6fd8, #5b8cff); }
    .fill.warn { background: linear-gradient(90deg, #d97706, #f3a43b); }
    .chart-box {
      width: 100%;
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 9px;
      background: #101720;
      padding: 10px;
    }
    .chart-box svg { display: block; width: 100%; min-width: 780px; height: auto; }
    .chart-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .mini-chart {
      border: 1px solid var(--line);
      border-radius: 9px;
      background: #101720;
      padding: 10px;
      min-width: 0;
    }
    .mini-chart svg { display: block; width: 100%; height: auto; }
    .chart-title { font-weight: 800; color: #e8f1ff; margin-bottom: 6px; }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      color: var(--muted);
      font-size: 13px;
      margin: 9px 0 0;
    }
    .legend span { display: inline-flex; align-items: center; gap: 6px; }
    .legend i { width: 18px; height: 3px; border-radius: 999px; display: inline-block; }
    .tradeoff-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
      margin-top: 12px;
    }
    .tradeoff-note {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .note-card {
      border: 1px solid var(--line);
      border-radius: 9px;
      background: #111722;
      padding: 12px;
    }
    .note-card strong { display: block; font-size: 24px; line-height: 1.15; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 10px 11px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: middle; }
    th { color: #dbeafe; background: #111722; position: sticky; top: 0; z-index: 1; }
    tr:last-child td { border-bottom: 0; }
    .table-scroll {
      max-height: 430px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 9px;
      background: #111722;
    }
    .table-scroll table { min-width: 980px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .muted { color: var(--muted); }
    .tag { display: inline-block; padding: 3px 7px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel2); color: #d6e1f2; font-size: 12px; }
    .delta { font-weight: 800; }
    .delta.good { color: var(--green); }
    .delta.bad { color: var(--red); }
    details { margin-top: 14px; }
    summary { cursor: pointer; color: #dbeafe; font-weight: 750; }
    .small-table th, .small-table td { padding: 8px 9px; }
    @media (max-width: 980px) {
      main { padding: 18px; }
      header, .hero, .section-grid { display: block; }
      .claim, .card { margin-bottom: 14px; }
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Critical Long-ring Results</h1>
      <div class="sub">Latest run: <span id="runTag" class="mono">loading</span> · critical-only · compression profile sweep · 4 domains · 2 templates · 2 models · rollout=60</div>
    </div>
    <div class="pill"><span id="runDot" class="dot"></span><span id="runText">loading</span></div>
  </header>

  <section class="hero">
    <div class="claim">
      <div class="claim-title">一句话结论</div>
      <div class="claim-text" id="claimText">正在读取最新结果...</div>
    </div>
    <div class="card">
      <h3>Run Status</h3>
      <div class="metric-grid" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
        <div>
          <div class="metric-label">Method records</div>
          <div class="metric-value"><span id="completed">-</span><span class="muted" style="font-size:18px">/<span id="expected">-</span></span></div>
        </div>
        <div>
          <div class="metric-label">Matched cases</div>
          <div class="metric-value" id="matched">-</div>
        </div>
      </div>
      <div class="sub" id="checkpoint">-</div>
    </div>
  </section>

  <section class="metric-grid" id="headlineCards"></section>

  <section class="card" style="margin-top:14px">
    <h2>Trade-off：压缩率牺牲是否值得</h2>
    <div class="sub">读法：上升的是风险覆盖收益，下降的是压缩率。只要绿色收益明显大于橙色代价，就说明牺牲的子图规模是可解释且划算的。</div>
    <div id="tradeoffNotes" class="tradeoff-note"></div>
    <div class="tradeoff-grid">
      <div>
        <h3>Overall Benefit vs Cost</h3>
        <div id="tradeoffBars" class="chart-box"></div>
      </div>
      <div>
        <h3>Domain × Size Trade-off Map</h3>
        <div id="tradeoffScatter" class="chart-box"></div>
      </div>
    </div>
    <div class="table-scroll" style="margin-top:12px; max-height:300px">
      <table>
        <thead><tr><th>Domain / Size</th><th>Root@3 gain</th><th>Risk-any gain</th><th>Risk-all gain</th><th>Compression cost</th><th>Cost-benefit read</th></tr></thead>
        <tbody id="tradeoffRows"></tbody>
      </table>
    </div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>SA-MCGS 60 Rollout 收敛总览</h2>
    <div class="sub">曲线是每个 rollout 当时的 dynamic core，不是最终 post-selection 后的总表；最重要看 Risk-any 是否快速升高、Risk-all 是否持续补齐、Effective OC 是否随搜索逐步增长。</div>
    <div id="overallConvergence" class="chart-box"></div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>按领域和 SCC 长度拆分的收敛曲线</h2>
    <div class="sub">长环如果曾经出现信号又被噪声淹没，这里能直接看出来。</div>
    <div id="sizeConvergenceCharts" class="chart-grid"></div>
  </section>

  <section class="section-grid">
    <div class="card">
      <h2>Core Metrics</h2>
      <div class="sub">绿色是 SA-MCGS，红色是 Naive direct subgraph。</div>
      <div id="bars"></div>
    </div>
    <div class="card">
      <h2>Mechanism Check</h2>
      <div class="sub">这里看的是持续性搜索是否真的在积累 critical pair 证据。</div>
      <div id="mechanism"></div>
    </div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>Where The Win Comes From</h2>
    <div class="sub">按真实 SCC 长度拆开看。长环尤其重要。</div>
    <div class="table-scroll">
      <table>
        <thead><tr><th>Domain / Size</th><th>Method</th><th>N</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Avg subgraph</th><th>Compression</th><th>Critical locked</th><th>Revisits</th></tr></thead>
        <tbody id="domainSizeRows"></tbody>
      </table>
    </div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>Convergence Milestones</h2>
    <div class="sub">first-any / first-all / first effective OC 越早，说明搜索越快收敛到风险区域。</div>
    <div class="table-scroll">
      <table>
        <thead><tr><th>Domain</th><th>Size</th><th>Template</th><th>Model</th><th>First any</th><th>First all</th><th>First effective OC</th><th>Final risk</th><th>Final core</th><th>Compression</th><th>Locked</th><th>Revisits</th></tr></thead>
        <tbody id="convergenceRows"></tbody>
      </table>
    </div>
  </section>

  <section class="section-grid">
    <div class="card">
      <h2>Template Robustness</h2>
      <div class="sub">四类 critical 注入模板下的稳定性。</div>
      <div class="table-scroll" style="max-height:320px">
        <table class="small-table">
          <thead><tr><th>Template</th><th>Method</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th></tr></thead>
          <tbody id="templateRows"></tbody>
        </table>
      </div>
    </div>
    <div class="card">
      <h2>Compression Trade-off</h2>
      <div class="sub">SA 为保住 critical endpoints，子图会更大；这是这轮最主要的代价。</div>
      <div id="compressionBox"></div>
    </div>
    <div class="card">
      <h2>Compression Profile</h2>
      <div class="sub">压缩参数 smoke 时重点看这里：Risk-all 是否保住、Compression 是否升高。</div>
      <div class="table-scroll" style="max-height:320px">
        <table class="small-table">
          <thead><tr><th>Profile</th><th>Method</th><th>N</th><th>Risk-any</th><th>Risk-all</th><th>Subgraph</th><th>Compression</th></tr></thead>
          <tbody id="profileRows"></tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="card" style="margin-top:14px">
    <h2>Matched Case Table</h2>
    <div class="sub">每行是同一 domain / size / template / model 的 Naive vs SA 对照。</div>
    <div class="table-scroll">
      <table>
        <thead><tr><th>Domain</th><th>Size</th><th>Template</th><th>Model</th><th>Root@3</th><th>Risk-any</th><th>Risk-all</th><th>Compression</th><th>Subgraph</th><th>SA OC</th></tr></thead>
        <tbody id="caseRows"></tbody>
      </table>
    </div>
  </section>

  <details class="card">
    <summary>Raw Run Metadata</summary>
    <div class="sub" style="margin: 10px 0">保留少量运行信息，不再占据主页面。</div>
    <div id="rawMeta" class="mono muted"></div>
  </details>
</main>

<script>
function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function pct(n) {
  if (!Number.isFinite(n)) return '-';
  return Math.round(n * 100) + '%';
}
function pp(n) {
  if (!Number.isFinite(n)) return '-';
  const v = Math.round(n * 100);
  return `${v >= 0 ? '+' : ''}${v}pp`;
}
function rateText(hit, total) {
  if (!total) return '-';
  return `${hit}/${total} (${pct(hit / total)})`;
}
function parseRateValue(text) {
  const m = String(text || '').match(/(\\d+)\\/(\\d+)/);
  if (!m) return NaN;
  const den = Number(m[2]);
  return den ? Number(m[1]) / den : NaN;
}
function parsePct(value) {
  if (value == null || value === '-') return NaN;
  return Number(String(value).replace('%', '')) / 100;
}
function parseSubgraph(value) {
  if (!value || value === '-') return NaN;
  const left = String(value).split('/')[0];
  return Number(left);
}
function isWin(cell) {
  return String(cell?.class || '').includes('win');
}
function cellValue(cell) {
  return esc(cell?.value ?? '-');
}
function methodAgg(records, method, filterFn = () => true) {
  const rows = records.filter(r => r.method === method && filterFn(r));
  const n = rows.length;
  const sumBool = key => rows.filter(r => r[key] === true).length;
  const comps = rows.map(r => parsePct(r.compression)).filter(Number.isFinite);
  const subs = rows.map(r => parseSubgraph(r.subgraph)).filter(Number.isFinite);
  const locked = rows.map(r => Number(r.critical_locked || 0)).filter(Number.isFinite);
  const revisits = rows.map(r => Number(r.critical_revisits || 0)).filter(Number.isFinite);
  const avg = arr => arr.length ? arr.reduce((a,b) => a + b, 0) / arr.length : NaN;
  return {
    n,
    root: sumBool('top3'),
    any: sumBool('risk_any'),
    all: sumBool('risk_all'),
    errors: rows.filter(r => r.error).length,
    comp: avg(comps),
    sub: avg(subs),
    locked: avg(locked),
    revisits: avg(revisits),
  };
}
function metricCard(title, naiveValue, saValue, note, stronger = 'sa') {
  const cls = stronger === 'sa' ? 'ok' : 'warn';
  return `<div class="metric-card">
    <div class="metric-label">${esc(title)}</div>
    <div class="metric-value"><span class="bad">${esc(naiveValue)}</span> <span class="muted">→</span> <span class="${cls}">${esc(saValue)}</span></div>
    <div class="metric-note">${esc(note)}</div>
  </div>`;
}
function tradeoffBarChart(items) {
  items = (items || []).filter(i => Number.isFinite(i.value));
  if (!items.length) return '<div class="muted">No trade-off data.</div>';
  const width = 760, height = 250;
  const left = 152, right = 70, top = 22, rowH = 43;
  const maxAbs = Math.max(.05, ...items.map(i => Math.abs(i.value)));
  const zero = left + (width - left - right) * .34;
  const scale = v => zero + (v / maxAbs) * (width - left - right) * .62;
  const axis = `<line x1="${zero}" y1="${top-4}" x2="${zero}" y2="${height-28}" stroke="rgba(219,234,254,.35)" />`;
  const rows = items.map((item, i) => {
    const y = top + i * rowH;
    const x1 = item.value >= 0 ? zero : scale(item.value);
    const x2 = item.value >= 0 ? scale(item.value) : zero;
    return `
      <text x="12" y="${y+22}" fill="#dbeafe" font-size="14" font-weight="750">${esc(item.label)}</text>
      <rect x="${x1}" y="${y+8}" width="${Math.max(2, x2-x1)}" height="18" rx="9" fill="${item.color}" opacity=".9" />
      <text x="${item.value >= 0 ? x2 + 8 : x1 - 8}" y="${y+22}" fill="${item.color}" font-size="14" font-weight="800" text-anchor="${item.value >= 0 ? 'start' : 'end'}">${pp(item.value)}</text>`;
  }).join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="tradeoff benefit cost chart">
    <rect width="${width}" height="${height}" rx="8" fill="#101720" />
    ${axis}${rows}
    <text x="${zero}" y="${height-8}" text-anchor="middle" fill="#9aa6b8" font-size="12">0</text>
    <text x="${left}" y="${height-8}" text-anchor="middle" fill="#9aa6b8" font-size="12">cost</text>
    <text x="${width-right}" y="${height-8}" text-anchor="middle" fill="#9aa6b8" font-size="12">benefit</text>
  </svg>`;
}
function tradeoffScatter(points) {
  if (!points.length) return '<div class="muted">No matched domain-size trade-off data.</div>';
  const width = 720, height = 310;
  const left = 58, right = 26, top = 24, bottom = 48;
  const maxX = Math.max(.05, ...points.map(p => Math.max(0, p.cost))) * 1.15;
  const minY = Math.min(0, ...points.map(p => p.riskAllGain)) - .05;
  const maxY = Math.max(.15, ...points.map(p => p.riskAllGain)) + .08;
  const x = v => left + (Math.max(0, v) / maxX) * (width - left - right);
  const y = v => top + (1 - ((v - minY) / (maxY - minY))) * (height - top - bottom);
  const colors = {bgb:'#5b8cff', cuad:'#12b981', wikipedia:'#f3a43b'};
  const grid = [0,.1,.2,.3,.4].filter(v => v <= maxX).map(v => `
    <line x1="${x(v)}" x2="${x(v)}" y1="${top}" y2="${height-bottom}" stroke="rgba(154,166,184,.12)" />
    <text x="${x(v)}" y="${height-26}" text-anchor="middle" fill="#9aa6b8" font-size="11">${pp(v).replace('+','')}</text>`).join('');
  const ygrid = [0,.25,.5,.75,1].filter(v => v >= minY && v <= maxY).map(v => `
    <line x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(154,166,184,.14)" />
    <text x="${left-8}" y="${y(v)+4}" text-anchor="end" fill="#9aa6b8" font-size="11">${pp(v)}</text>`).join('');
  const dots = points.map(p => {
    const domain = String(p.label).split(':')[0];
    const color = colors[domain] || '#9b6cff';
    return `<g>
      <circle cx="${x(p.cost)}" cy="${y(p.riskAllGain)}" r="7" fill="${color}" opacity=".9" />
      <text x="${x(p.cost)+10}" y="${y(p.riskAllGain)+4}" fill="#dbeafe" font-size="12" font-weight="750">${esc(p.label)}</text>
    </g>`;
  }).join('');
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="domain size tradeoff scatter">
    <rect width="${width}" height="${height}" rx="8" fill="#101720" />
    ${grid}${ygrid}
    <line x1="${left}" x2="${width-right}" y1="${y(0)}" y2="${y(0)}" stroke="rgba(219,234,254,.45)" />
    <line x1="${left}" x2="${left}" y1="${top}" y2="${height-bottom}" stroke="rgba(219,234,254,.45)" />
    ${dots}
    <text x="${width/2}" y="${height-6}" text-anchor="middle" fill="#9aa6b8" font-size="12">compression cost: Naive compression - SA compression</text>
    <text transform="translate(15 ${height/2}) rotate(-90)" text-anchor="middle" fill="#9aa6b8" font-size="12">Risk-all gain</text>
  </svg>
  <div class="legend"><span><i style="background:#5b8cff"></i>BGB</span><span><i style="background:#12b981"></i>CUAD</span></div>`;
}
function buildDomainSizeTradeoffs(sizeGroups) {
  const byLabel = {};
  for (const row of sizeGroups || []) {
    const slot = byLabel[row.label] || (byLabel[row.label] = {});
    slot[row.method] = row;
  }
  return Object.entries(byLabel).map(([label, methods]) => {
    const n = methods.naive, sa = methods['sa-mcgs'];
    if (!n || !sa) return null;
    const rootGain = parseRateValue(sa.root_top3) - parseRateValue(n.root_top3);
    const anyGain = parseRateValue(sa.risk_any) - parseRateValue(n.risk_any);
    const allGain = parseRateValue(sa.risk_all) - parseRateValue(n.risk_all);
    const cost = parsePct(n.avg_compression) - parsePct(sa.avg_compression);
    return { label, rootGain, anyGain, riskAllGain: allGain, cost };
  }).filter(Boolean);
}
function bar(label, naiveHit, naiveN, saHit, saN) {
  const nv = naiveN ? naiveHit / naiveN : 0;
  const sv = saN ? saHit / saN : 0;
  return `<div>
    <div class="bar-row"><div>${esc(label)} · Naive</div><div class="track"><div class="fill naive" style="width:${Math.round(nv*100)}%"></div></div><div class="bad">${rateText(naiveHit, naiveN)}</div></div>
    <div class="bar-row"><div>${esc(label)} · SA</div><div class="track"><div class="fill sa" style="width:${Math.round(sv*100)}%"></div></div><div class="ok">${rateText(saHit, saN)}</div></div>
  </div>`;
}
function profileBarChart(rows) {
  rows = (rows || []).filter(r => r.method === 'sa-mcgs');
  if (!rows.length) return '<div class="muted">No compression profile data.</div>';
  return rows.map(r => {
    const riskAll = parseRateValue(r.risk_all);
    const riskAny = parseRateValue(r.risk_any);
    const comp = parsePct(r.avg_compression);
    return `<div class="profile-bars">
      <div class="bar-row"><div><strong>${esc(r.label)}</strong> · Risk-all</div><div class="track"><div class="fill sa" style="width:${Math.round((riskAll || 0) * 100)}%"></div></div><div class="${riskAll >= .8 ? 'ok' : riskAll >= .55 ? 'warn' : 'bad'}">${esc(r.risk_all)}</div></div>
      <div class="bar-row"><div>${esc(r.label)} · Risk-any</div><div class="track"><div class="fill blue" style="width:${Math.round((riskAny || 0) * 100)}%"></div></div><div class="${riskAny >= .9 ? 'ok' : 'warn'}">${esc(r.risk_any)}</div></div>
      <div class="bar-row"><div>${esc(r.label)} · Compression</div><div class="track"><div class="fill warn" style="width:${Math.round((comp || 0) * 100)}%"></div></div><div class="warn">${esc(r.avg_compression)}</div></div>
    </div>`;
  }).join('');
}
function rowClassFromRate(text) {
  const m = String(text || '').match(/\\((\\d+)%\\)/);
  if (!m) return '';
  const v = Number(m[1]);
  if (v >= 80) return 'ok';
  if (v <= 35) return 'bad';
  return 'warn';
}
function clamp01(v) {
  if (!Number.isFinite(v)) return null;
  return Math.max(0, Math.min(1, v));
}
function chartPath(series, key, x, y) {
  const pts = (series || [])
    .map(p => ({x: x(Number(p.rollout)), y: y(clamp01(Number(p[key])))}))
    .filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (!pts.length) return '';
  return pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
}
function lineChart(series, lines, opts = {}) {
  const clean = (series || []).filter(p => Number.isFinite(Number(p.rollout)));
  if (!clean.length) return '<div class="muted">No convergence trace saved yet.</div>';
  const width = opts.width || 980;
  const height = opts.height || 330;
  const left = 54, right = 20, top = 26, bottom = 42;
  const maxRollout = Math.max(60, ...clean.map(p => Number(p.rollout)));
  const x = r => left + ((r - 1) / Math.max(1, maxRollout - 1)) * (width - left - right);
  const y = v => top + (1 - v) * (height - top - bottom);
  const yTicks = [0, .25, .5, .75, 1];
  const xTicks = [1, 15, 30, 45, 60].filter(v => v <= maxRollout);
  const gridY = yTicks.map(v => `
    <line x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(154,166,184,.18)" />
    <text x="${left-10}" y="${y(v)+4}" text-anchor="end" fill="#9aa6b8" font-size="12">${Math.round(v*100)}%</text>`).join('');
  const gridX = xTicks.map(v => `
    <line x1="${x(v)}" x2="${x(v)}" y1="${top}" y2="${height-bottom}" stroke="rgba(154,166,184,.12)" />
    <text x="${x(v)}" y="${height-16}" text-anchor="middle" fill="#9aa6b8" font-size="12">${v}</text>`).join('');
  const paths = lines.map(line => {
    const d = chartPath(clean, line.key, x, y);
    return d ? `<path d="${d}" fill="none" stroke="${line.color}" stroke-width="${line.width || 4}" stroke-linecap="round" stroke-linejoin="round" />` : '';
  }).join('');
  const latest = lines.map((line, i) => {
    const last = [...clean].reverse().find(p => Number.isFinite(Number(p[line.key])));
    const value = last ? pct(Number(last[line.key])) : '-';
    return `<text x="${left + 8}" y="${top + 18 + i * 18}" fill="${line.color}" font-size="13" font-weight="750">${esc(line.label)}: ${value}</text>`;
  }).join('');
  const legend = `<div class="legend">${lines.map(l => `<span><i style="background:${l.color}"></i>${esc(l.label)}</span>`).join('')}</div>`;
  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="convergence chart">
      <rect x="0" y="0" width="${width}" height="${height}" rx="8" fill="#101720" />
      ${gridY}${gridX}
      <line x1="${left}" x2="${width-right}" y1="${height-bottom}" y2="${height-bottom}" stroke="rgba(219,234,254,.45)" />
      <line x1="${left}" x2="${left}" y1="${top}" y2="${height-bottom}" stroke="rgba(219,234,254,.45)" />
      ${paths}
      ${latest}
      <text x="${width/2}" y="${height-4}" text-anchor="middle" fill="#9aa6b8" font-size="12">rollout</text>
    </svg>${legend}`;
}
function renderConvergence(conv) {
  const overallLines = [
    {key:'risk_any_rate', label:'Trace risk-any', color:'#12b981'},
    {key:'risk_all_rate', label:'Trace risk-all', color:'#9b6cff'},
    {key:'effective_oc_rate', label:'Effective OC rate', color:'#ef4e4e'},
    {key:'risk_coverage', label:'Risk coverage', color:'#5b8cff'},
    {key:'compression', label:'Compression', color:'#f3a43b', width:3},
  ];
  const miniLines = [
    {key:'risk_coverage', label:'Risk coverage', color:'#5b8cff'},
    {key:'risk_all_rate', label:'Risk-all', color:'#9b6cff'},
    {key:'effective_oc_rate', label:'Effective OC', color:'#ef4e4e'},
    {key:'compression', label:'Compression', color:'#f3a43b', width:3},
  ];
  document.getElementById('overallConvergence').innerHTML = lineChart(conv?.overall || [], overallLines, {height: 350});
  const entries = Object.entries(conv?.by_domain_size || {});
  document.getElementById('sizeConvergenceCharts').innerHTML = entries.map(([label, series]) => `
    <div class="mini-chart">
      <div class="chart-title">${esc(label)}</div>
      ${lineChart(series, miniLines, {height: 260})}
    </div>`).join('') || '<div class="muted">No domain/size convergence trace yet.</div>';
}
async function refresh() {
  const res = await fetch('/api/progress?ts=' + Date.now());
  const data = await res.json();
  const s = data.summary || {};
  const records = s.recent || [];
  const naive = methodAgg(records, 'naive');
  const sa = methodAgg(records, 'sa-mcgs');
  const longFilter = r => Number(r.size) >= 25;
  const naiveLong = methodAgg(records, 'naive', longFilter);
  const saLong = methodAgg(records, 'sa-mcgs', longFilter);

  document.getElementById('runDot').className = 'dot ' + (data.process?.running ? 'on' : 'done');
  document.getElementById('runText').textContent = data.process?.running ? 'running' : 'completed';
  document.getElementById('completed').textContent = s.completed_total ?? '-';
  document.getElementById('expected').textContent = s.expected_total ?? '-';
  document.getElementById('matched').textContent = s.matched_cases ?? '-';
  document.getElementById('checkpoint').textContent = `checkpoint: ${data.checkpoint_mtime || '-'} · errors: ${s.error_total ?? 0}`;
  const runTag = data.checkpoint
    ? data.checkpoint.split('/').pop().replace('_severity_grid_status.json', '')
    : 'no-status-file';
  document.getElementById('runTag').textContent = runTag;

  const saOnlySweep = naive.n === 0 && sa.n > 0;
  const profileRows = (s.profile_groups || []).filter(r => r.method === 'sa-mcgs');
  const bestRiskAllProfile = [...profileRows].sort((a, b) =>
    (parseRateValue(b.risk_all) - parseRateValue(a.risk_all)) ||
    (parsePct(b.avg_compression) - parsePct(a.avg_compression))
  )[0];
  const bestCompressionProfile = [...profileRows].sort((a, b) =>
    (parsePct(b.avg_compression) - parsePct(a.avg_compression)) ||
    (parseRateValue(b.risk_all) - parseRateValue(a.risk_all))
  )[0];

  if (saOnlySweep) {
    document.getElementById('claimText').innerHTML =
      `这轮是 <strong>SA-only compression profile sweep</strong>：共 <strong>${sa.n}</strong> 条 critical SA 记录。` +
      `整体 <strong>Root@3=${rateText(sa.root, sa.n)}</strong>、<strong>Risk-any=${rateText(sa.any, sa.n)}</strong>、` +
      `<strong>Risk-all=${rateText(sa.all, sa.n)}</strong>，平均 core 压缩率 <strong>${pct(sa.comp)}</strong>。` +
      (bestRiskAllProfile
        ? `当前 Risk-all 最稳的是 <strong>${esc(bestRiskAllProfile.label)}</strong>：${esc(bestRiskAllProfile.risk_all)}，压缩率 ${esc(bestRiskAllProfile.avg_compression)}。`
        : '');
    document.getElementById('headlineCards').innerHTML = [
      metricCard('Root@3', '-', rateText(sa.root, sa.n), '事故 root 进入前三的能力'),
      metricCard('Risk-any', '-', rateText(sa.any, sa.n), '至少保住一个可修复风险入口'),
      metricCard('Risk-all', '-', rateText(sa.all, sa.n), 'critical 场景最重要：两端风险收齐'),
      metricCard(
        'Best compression',
        '-',
        bestCompressionProfile ? `${bestCompressionProfile.label}: ${bestCompressionProfile.avg_compression}` : '-',
        '压缩率最高的 profile，同时要看 Risk-all 是否掉太多'
      ),
    ].join('');
  } else {
    document.getElementById('claimText').innerHTML =
      `在 <strong>${sa.n}</strong> 个 matched critical case 中，SA-MCGS 的 ` +
      `<strong>Root@3=${rateText(sa.root, sa.n)}</strong>、<strong>Risk-any=${rateText(sa.any, sa.n)}</strong>、` +
      `<strong>Risk-all=${rateText(sa.all, sa.n)}</strong>，明显高于 Naive 的 ` +
      `<strong>Root@3=${rateText(naive.root, naive.n)}</strong>、<strong>Risk-all=${rateText(naive.all, naive.n)}</strong>。` +
      `代价是 SA core 子图更大，平均压缩率从 Naive 的 <strong>${pct(naive.comp)}</strong> 降到 <strong>${pct(sa.comp)}</strong>。`;

    document.getElementById('headlineCards').innerHTML = [
      metricCard('Root@3', rateText(naive.root, naive.n), rateText(sa.root, sa.n), '事故 root 进入前三的能力'),
      metricCard('Risk-any', rateText(naive.any, naive.n), rateText(sa.any, sa.n), '至少保住一个可修复风险入口'),
      metricCard('Risk-all', rateText(naive.all, naive.n), rateText(sa.all, sa.n), 'critical 场景最重要：两端风险收齐'),
      metricCard('Long-ring Root@3', rateText(naiveLong.root, naiveLong.n), rateText(saLong.root, saLong.n), '25-node 长环上差距最大'),
    ].join('');
  }

  const rootGain = sa.n && naive.n ? sa.root / sa.n - naive.root / naive.n : NaN;
  const anyGain = sa.n && naive.n ? sa.any / sa.n - naive.any / naive.n : NaN;
  const allGain = sa.n && naive.n ? sa.all / sa.n - naive.all / naive.n : NaN;
  const compCost = naive.comp - sa.comp;
  const longRootGain = saLong.n && naiveLong.n ? saLong.root / saLong.n - naiveLong.root / naiveLong.n : NaN;
  const longAllGain = saLong.n && naiveLong.n ? saLong.all / saLong.n - naiveLong.all / naiveLong.n : NaN;
  const payoff = compCost > 0 ? allGain / compCost : NaN;
  if (saOnlySweep) {
    document.getElementById('tradeoffNotes').innerHTML = profileRows.map(r => `
      <div class="note-card">
        <span class="muted">${esc(r.label)}</span>
        <strong class="${rowClassFromRate(r.risk_all) || 'warn'}">${esc(r.risk_all)}</strong>
        <span class="sub">Risk-all；压缩率 ${esc(r.avg_compression)}，平均 ${esc(r.avg_subgraph)} 个节点</span>
      </div>`).join('');
    document.getElementById('tradeoffBars').innerHTML = profileBarChart(profileRows);
    document.getElementById('tradeoffScatter').innerHTML = '<div class="muted">这轮没有 Naive matched rows；散点收益图留给 Naive-vs-SA 正式表使用。</div>';
    document.getElementById('tradeoffRows').innerHTML = profileRows.map(r => `
      <tr>
        <td><span class="tag">${esc(r.label)}</span></td>
        <td class="${rowClassFromRate(r.root_top3)}">${esc(r.root_top3)}</td>
        <td class="${rowClassFromRate(r.risk_any)}">${esc(r.risk_any)}</td>
        <td class="${rowClassFromRate(r.risk_all)}">${esc(r.risk_all)}</td>
        <td class="warn">${esc(r.avg_compression)}</td>
        <td>${esc(r.avg_subgraph)} nodes avg</td>
      </tr>`).join('');
    document.getElementById('bars').innerHTML = profileBarChart(profileRows);
  } else {
    document.getElementById('tradeoffNotes').innerHTML = `
      <div class="note-card"><span class="muted">Risk-all gain</span><strong class="ok">${pp(allGain)}</strong><span class="sub">critical 两端收齐提升</span></div>
      <div class="note-card"><span class="muted">Compression cost</span><strong class="warn">-${pp(compCost).replace('+','')}</strong><span class="sub">平均压缩率下降</span></div>
      <div class="note-card"><span class="muted">Long-ring Root@3</span><strong class="ok">${pp(longRootGain)}</strong><span class="sub">25-node 长环提升</span></div>
      <div class="note-card"><span class="muted">Risk-all payoff</span><strong class="${payoff >= 1 ? 'ok' : 'warn'}">${Number.isFinite(payoff) ? payoff.toFixed(1) + 'x' : '-'}</strong><span class="sub">每 1pp 压缩代价换来的 Risk-all 收益</span></div>`;
    document.getElementById('tradeoffBars').innerHTML = tradeoffBarChart([
      {label:'Root@3 gain', value: rootGain, color:'#12b981'},
      {label:'Risk-any gain', value: anyGain, color:'#12b981'},
      {label:'Risk-all gain', value: allGain, color:'#12b981'},
      {label:'Long-ring root gain', value: longRootGain, color:'#5b8cff'},
      {label:'Compression cost', value: -compCost, color:'#f3a43b'},
    ]);
    const tradeoffPoints = buildDomainSizeTradeoffs(s.size_groups || []);
    document.getElementById('tradeoffScatter').innerHTML = tradeoffScatter(tradeoffPoints);
    document.getElementById('tradeoffRows').innerHTML = tradeoffPoints.map(p => {
      const ratio = p.cost > 0 ? p.riskAllGain / p.cost : NaN;
      const read = !Number.isFinite(ratio)
        ? '压缩没有明显代价'
        : ratio >= 1
        ? `收益明显大于代价 (${ratio.toFixed(1)}x)`
        : ratio >= 0.35
        ? `收益存在，但代价偏高 (${ratio.toFixed(1)}x)`
        : `这一组主要是压缩代价，收益弱 (${ratio.toFixed(1)}x)`;
      return `<tr>
        <td><span class="tag">${esc(p.label)}</span></td>
        <td class="${p.rootGain >= 0 ? 'ok' : 'bad'}">${pp(p.rootGain)}</td>
        <td class="${p.anyGain >= 0 ? 'ok' : 'bad'}">${pp(p.anyGain)}</td>
        <td class="${p.riskAllGain >= 0 ? 'ok' : 'bad'}">${pp(p.riskAllGain)}</td>
        <td class="warn">-${pp(p.cost).replace('+','')}</td>
        <td class="${ratio >= 1 ? 'ok' : ratio >= .35 ? 'warn' : 'bad'}">${esc(read)}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="6" class="muted">No trade-off rows.</td></tr>';

    document.getElementById('bars').innerHTML = [
      bar('Root@3', naive.root, naive.n, sa.root, sa.n),
      bar('Risk-any', naive.any, naive.n, sa.any, sa.n),
      bar('Risk-all', naive.all, naive.n, sa.all, sa.n),
    ].join('');
  }

  renderConvergence(s.convergence || {});

  document.getElementById('mechanism').innerHTML = `
    <div class="metric-grid" style="grid-template-columns: repeat(2, minmax(0, 1fr));">
      <div class="metric-card"><div class="metric-label">Avg locked critical pairs</div><div class="metric-value ok">${sa.locked.toFixed(1)}</div><div class="metric-note">说明 critical pair 被多轮确认后稳定进入 ledger。</div></div>
      <div class="metric-card"><div class="metric-label">Avg revisit windows</div><div class="metric-value blue">${sa.revisits.toFixed(1)}</div><div class="metric-note">发现可疑 pair 后，搜索会主动回访这条路径。</div></div>
      <div class="metric-card"><div class="metric-label">SA avg core size</div><div class="metric-value warn">${sa.sub.toFixed(1)}</div><div class="metric-note">更大的 core 换来更高 risk-all。</div></div>
      <div class="metric-card"><div class="metric-label">SA compression</div><div class="metric-value warn">${pct(sa.comp)}</div><div class="metric-note">当前主要 trade-off。</div></div>
    </div>`;

  const sizeRows = (s.size_groups || []).map(r => {
    const methodClass = r.method === 'sa-mcgs' ? 'ok' : 'bad';
    const extra = r.method === 'sa-mcgs'
      ? (() => {
          const rs = records.filter(x => `${x.domain}:${x.size}` === r.label && x.method === 'sa-mcgs');
          const a = methodAgg(rs, 'sa-mcgs');
          return `<td>${Number.isFinite(a.locked) ? a.locked.toFixed(1) : '-'}</td><td>${Number.isFinite(a.revisits) ? a.revisits.toFixed(1) : '-'}</td>`;
        })()
      : '<td>-</td><td>-</td>';
    return `<tr>
      <td><span class="tag">${esc(r.label)}</span></td><td class="${methodClass}">${esc(r.method)}</td><td>${esc(r.count)}</td>
      <td class="${rowClassFromRate(r.root_top3)}">${esc(r.root_top3)}</td>
      <td class="${rowClassFromRate(r.risk_any)}">${esc(r.risk_any)}</td>
      <td class="${rowClassFromRate(r.risk_all)}">${esc(r.risk_all)}</td>
      <td>${esc(r.avg_subgraph)}</td><td>${esc(r.avg_compression)}</td>${extra}
    </tr>`;
  }).join('');
  document.getElementById('domainSizeRows').innerHTML = sizeRows || '<tr><td colspan="10" class="muted">No data.</td></tr>';

  document.getElementById('convergenceRows').innerHTML = ((s.convergence || {}).cases || []).map(r => {
    const firstAllClass = r.first_all ? (Number(r.first_all) <= 18 ? 'ok' : 'warn') : 'bad';
    const riskClass = r.final_risk_all === true ? 'ok' : 'bad';
    return `<tr>
      <td>${esc(r.domain)}</td><td>${esc(r.size)}</td><td><span class="tag">${esc(r.template)}</span></td><td>${esc(r.model)}</td>
      <td class="${r.first_any ? 'ok' : 'bad'}">${esc(r.first_any || '-')}</td>
      <td class="${firstAllClass}">${esc(r.first_all || '-')}</td>
      <td class="${r.first_effective_oc ? 'ok' : 'bad'}">${esc(r.first_effective_oc || '-')}</td>
      <td class="${riskClass}">${pct(Number(r.final_risk_coverage))}</td>
      <td class="mono">${esc(r.final_subgraph_size || '-')}</td>
      <td>${pct(Number(r.final_compression))}</td>
      <td>${esc(r.locked)}</td><td>${esc(r.revisits)}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="12" class="muted">No SA convergence milestones.</td></tr>';

  document.getElementById('templateRows').innerHTML = (s.template_groups || []).map(r => `
    <tr><td><span class="tag">${esc(r.label)}</span></td><td class="${r.method === 'sa-mcgs' ? 'ok' : 'bad'}">${esc(r.method)}</td>
    <td class="${rowClassFromRate(r.root_top3)}">${esc(r.root_top3)}</td>
    <td class="${rowClassFromRate(r.risk_any)}">${esc(r.risk_any)}</td>
    <td class="${rowClassFromRate(r.risk_all)}">${esc(r.risk_all)}</td></tr>`).join('');

  document.getElementById('profileRows').innerHTML = (s.profile_groups || []).map(r => `
    <tr><td><span class="tag">${esc(r.label)}</span></td><td class="${r.method === 'sa-mcgs' ? 'ok' : 'bad'}">${esc(r.method)}</td>
    <td>${esc(r.count)}</td>
    <td class="${rowClassFromRate(r.risk_any)}">${esc(r.risk_any)}</td>
    <td class="${rowClassFromRate(r.risk_all)}">${esc(r.risk_all)}</td>
    <td>${esc(r.avg_subgraph)}</td><td>${esc(r.avg_compression)}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">No profile data.</td></tr>';

  document.getElementById('compressionBox').innerHTML = `
    <div class="bar-row"><div>Naive</div><div class="track"><div class="fill naive" style="width:${Math.round(naive.comp*100)}%"></div></div><div class="bad">${pct(naive.comp)}</div></div>
    <div class="bar-row"><div>SA-MCGS</div><div class="track"><div class="fill sa" style="width:${Math.round(sa.comp*100)}%"></div></div><div class="warn">${pct(sa.comp)}</div></div>
    <p class="sub">读法：压缩率越高，子图越小。SA 这轮为了收齐 critical root+witness，牺牲了约 ${Math.round((naive.comp - sa.comp) * 100)} 个百分点压缩率，但 Risk-all 从 ${rateText(naive.all, naive.n)} 提升到 ${rateText(sa.all, sa.n)}。</p>`;

  const pairwise = s.pairwise || [];
  document.getElementById('caseRows').innerHTML = pairwise.map(r => `
    <tr>
      <td>${esc(r.domain)}</td><td>${esc(r.size)}</td><td><span class="tag">${esc(r.template)}</span></td><td>${esc(r.model)}</td>
      <td><span class="bad">N:${cellValue(r.root_naive)}</span> / <span class="ok">SA:${cellValue(r.root_sa)}</span></td>
      <td><span class="bad">N:${cellValue(r.any_naive)}</span> / <span class="ok">SA:${cellValue(r.any_sa)}</span></td>
      <td><span class="bad">N:${cellValue(r.all_naive)}</span> / <span class="ok">SA:${cellValue(r.all_sa)}</span></td>
      <td><span class="bad">${cellValue(r.comp_naive)}</span> / <span class="ok">${cellValue(r.comp_sa)}</span></td>
      <td><span class="bad">${esc(r.naive_subgraph)}</span> / <span class="ok">${esc(r.sa_subgraph)}</span></td>
      <td>${esc(r.oc)}</td>
    </tr>`).join('') || '<tr><td colspan="10" class="muted">No matched cases.</td></tr>';

  document.getElementById('rawMeta').innerHTML =
    `status: ${esc(JSON.stringify(data.task_summary || {}))}<br>` +
    `domains: ${esc(JSON.stringify(s.by_domain || {}))}<br>` +
    `methods: ${esc(JSON.stringify(s.by_method || {}))}<br>` +
    `sizes: ${esc(JSON.stringify(s.sizes || {}))}<br>` +
    `checkpoint: ${esc(data.checkpoint || '-')}`;
}
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    args: argparse.Namespace

    def _send(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/progress"):
            payload = _payload(self.args)
            self._send(200, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        if self.path.startswith("/analysis"):
            html_path = RESULTS_DIR / "SEVERITY_GRID_ANALYSIS.html"
            if html_path.exists():
                self._send(200, html_path.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, b"analysis report not found", "text/plain; charset=utf-8")
            return
        if self.path.startswith("/figures/"):
            name = Path(self.path.split("?", 1)[0]).name
            image_path = RESULTS_DIR / "figures" / name
            if image_path.exists() and image_path.suffix.lower() == ".png":
                self._send(200, image_path.read_bytes(), "image/png")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        self._send(200, _clean_html().encode(), "text/html; charset=utf-8")

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument(
        "--status-file",
        help="Optional severity-grid status JSON. When set, aggregate result files listed there.",
    )
    parser.add_argument(
        "--result-glob",
        default="battle_inject_*longrings_b60_cuad12to26_wiki34_bgb11to25_*.partial.json",
    )
    parser.add_argument("--expected-total", type=int, default=52)
    parser.add_argument("--process-match", default="longrings_b60_cuad12to26_wiki34_bgb11to25")
    args = parser.parse_args()
    Handler.args = args
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Progress dashboard: http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
