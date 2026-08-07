#!/usr/bin/env python3
"""Serve a live dashboard for the 40-case cost audit run."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
DISCUSSION = ROOT / "emnlp2026_discussion"
HERE = Path(__file__).resolve().parent

LABEL = "com.mcgs.costaudit.40case.gpt4o.flash.20260712"
RUNS = {
    "gpt-4o": DISCUSSION / "cost_audit_runs/clean_40case_gpt4o_b50_20260712",
    "gemini-2.5-flash": DISCUSSION
    / "cost_audit_runs/clean_40case_gemini25flash_b50_20260712",
}
LAUNCH_LOG = DISCUSSION / "cost_audit_runs/cost_audit_40case_gpt4o_flash.launch.log"


def safe_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}", "_path": str(path)}


def safe_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def tail_text(path: Path, lines: int = 30, max_bytes: int = 40000) -> list[str]:
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            fh.seek(max(0, size - max_bytes))
            data = fh.read().decode("utf-8", errors="replace")
        return data.splitlines()[-lines:]
    except Exception as exc:
        return [f"{type(exc).__name__}: {exc}"]


def tail_jsonl(path: Path, lines: int = 24) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in tail_text(path, lines=lines * 2, max_bytes=160000):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows[-lines:]


def float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def parse_time(value: Any) -> float | None:
    if not value:
        return None
    text = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except Exception:
            pass
    return None


def summarize_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    ok_calls = [c for c in calls if c.get("ok")]
    runtimes = [float_or_none(c.get("runtime_sec")) for c in ok_calls]
    runtimes = [r for r in runtimes if r is not None]
    tokens = [
        float_or_none((c.get("usage") or {}).get("total_tokens"))
        for c in ok_calls
    ]
    tokens = [t for t in tokens if t is not None]
    last_end = max((parse_time(c.get("ended_at")) or 0 for c in calls), default=0)
    return {
        "logged_calls": len(calls),
        "ok_calls": len(ok_calls),
        "avg_runtime_sec_recent": sum(runtimes) / len(runtimes) if runtimes else None,
        "avg_total_tokens_recent": sum(tokens) / len(tokens) if tokens else None,
        "last_call_ended_at": datetime.fromtimestamp(last_end).astimezone().isoformat()
        if last_end
        else None,
    }


def launch_status() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except Exception as exc:
        return {"loaded": False, "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"loaded": False, "error": proc.stderr.strip() or proc.stdout.strip()}
    info: dict[str, Any] = {"loaded": True, "label": LABEL}
    for line in proc.stdout.splitlines():
        if line.startswith("\tstate = "):
            info["state"] = line.split("=", 1)[1].strip()
        elif line.startswith("\tpid = "):
            info["pid"] = line.split("=", 1)[1].strip()
        elif line.startswith("\tlast exit code = "):
            info["last_exit_code"] = line.split("=", 1)[1].strip()
        elif line.startswith("\truns = "):
            info["runs"] = line.split("=", 1)[1].strip()
    return info


def load_run(model: str, run_dir: Path) -> dict[str, Any]:
    status = safe_json(run_dir / "status.json")
    call_log = Path(status.get("call_log") or run_dir / "call_logs/llm_calls.jsonl")
    recent_calls = tail_jsonl(call_log, lines=24)
    summary_rows = safe_csv(run_dir / "summary_cost_table.csv")
    method_cases = safe_csv(run_dir / "summary_method_cases.csv")
    completed = int(status.get("completed_method_cases") or 0)
    total = int(status.get("total_method_cases") or 0)
    remaining = int(status.get("remaining_method_cases") or max(0, total - completed))
    current = status.get("current")
    eta_seconds = None
    if completed and remaining:
        runtimes: list[float] = []
        for row in method_cases:
            runtime = float_or_none(row.get("runtime_sec"))
            if runtime is not None and runtime > 0:
                runtimes.append(runtime)
        if runtimes:
            eta_seconds = sum(runtimes) / len(runtimes) * remaining
    current_age_sec = None
    if isinstance(current, dict):
        started = parse_time(current.get("started_at"))
        if started:
            current_age_sec = max(0, time.time() - started)
    return {
        "model": model,
        "run_dir": str(run_dir),
        "status": status,
        "progress": {
            "completed": completed,
            "total": total,
            "remaining": remaining,
            "failed": int(status.get("failed_method_cases") or 0),
            "percent": (100 * completed / total) if total else 0,
            "eta_seconds": eta_seconds,
            "current_age_sec": current_age_sec,
        },
        "summary_cost_table": summary_rows,
        "summary_method_cases_tail": method_cases[-18:],
        "method_case_count": len(method_cases),
        "recent_calls": recent_calls,
        "recent_call_summary": summarize_calls(recent_calls),
    }


def build_payload() -> dict[str, Any]:
    runs = [load_run(model, run_dir) for model, run_dir in RUNS.items()]
    total_done = sum(run["progress"]["completed"] for run in runs)
    total_cases = sum(run["progress"]["total"] for run in runs)
    total_failed = sum(run["progress"]["failed"] for run in runs)
    active = next(
        (
            run
            for run in runs
            if run["progress"]["remaining"] > 0
            and run["status"].get("current") is not None
        ),
        None,
    )
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "launch_agent": launch_status(),
        "overall": {
            "completed": total_done,
            "total": total_cases,
            "remaining": max(0, total_cases - total_done),
            "failed": total_failed,
            "percent": (100 * total_done / total_cases) if total_cases else 0,
            "active_model": active["model"] if active else None,
        },
        "runs": runs,
        "launch_log_tail": tail_text(LAUNCH_LOG, lines=24),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self.send_bytes(
                (HERE / "index.html").read_bytes(),
                "text/html; charset=utf-8",
            )
            return
        if path == "/api/status":
            body = json.dumps(build_payload(), ensure_ascii=False).encode("utf-8")
            self.send_bytes(body, "application/json; charset=utf-8")
            return
        self.send_bytes(b"not found", "text/plain; charset=utf-8", status=404)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving cost audit live dashboard on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
