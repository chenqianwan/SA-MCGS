#!/Users/chenlong/.pyenv/versions/3.11.0/bin/python
"""Monitor already launched LEA workers; never launch/retry model API jobs.

Only live_status.json and the read-only summary outputs are written. Latest
launches, OS process identity, terminal artifacts and the shared budget status
are inspected. Old smoke launches cannot count as current workers.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = Path("/Users/chenlong/.pyenv/versions/3.11.0/bin/python")
TERMINAL_RESULTS = {"complete", "strict_experiment_failure"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def atomic_write(path: Path, payload: dict) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def stamp(record: dict) -> float:
    return datetime.fromisoformat(record["started_at"].replace("Z", "+00:00")).timestamp()


def phase(record: dict) -> str:
    text = record.get("phase", "")
    return "smoke" if text.startswith("smoke") else text


def select_current_launches(records: list[dict]) -> tuple[list[dict], list[dict]]:
    eligible = [row for row in records if phase(row) in {"run", "smoke"}]
    by_model = defaultdict(list)
    for row in eligible:
        by_model[row["model"]].append(row)
    selected = []
    for rows in by_model.values():
        newest = max(rows, key=stamp)
        current_phase = phase(newest)
        shards = int(newest.get("shard_count", 1))
        candidates = [row for row in rows if phase(row) == current_phase
                      and int(row.get("shard_count", 1)) == shards]
        by_shard = {}
        for row in sorted(candidates, key=stamp):
            by_shard[int(row.get("shard_index", 0))] = row
        selected.extend(by_shard.values())
    selected_keys = {(row["pid"], row["started_at"]) for row in selected}
    superseded = [row for row in eligible if (row["pid"], row["started_at"]) not in selected_keys]
    return sorted(selected, key=lambda row: (row["model"], int(row.get("shard_index", 0)))), superseded


def inspect_process(record: dict) -> dict:
    pid = int(record["pid"])
    answer = {"pid": pid, "alive": False, "process_check": "not_found"}
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return answer
    except PermissionError:
        answer["process_check"] = "exists_but_permission_denied"
        return answer
    query = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", "stat=", "-o", "lstart=", "-o", "command="],
        capture_output=True, text=True, timeout=5,
        env={**os.environ, "LC_ALL": "C"},
    )
    fields = query.stdout.strip().split(None, 6)
    if query.returncode or len(fields) < 7:
        answer["process_check"] = "exited_during_check"
        return answer
    state, started, command = fields[0], " ".join(fields[1:6]), fields[6]
    if state.startswith("Z"):
        answer["process_check"] = "zombie"
        return answer
    if "run_completion.py" not in command or record["model"] not in command:
        answer["process_check"] = "pid_reused_or_different_command"
        return answer
    try:
        process_start = datetime.strptime(started, "%a %b %d %H:%M:%S %Y").astimezone().timestamp()
        if abs(process_start - stamp(record)) > 120:
            answer["process_check"] = "pid_start_time_mismatch"
            return answer
    except ValueError:
        answer["process_check"] = "unparseable_process_start"
        return answer
    answer.update({"alive": True, "process_check": "os_pid_command_start_verified", "os_state": state})
    return answer


class Monitor:
    def __init__(self, directory: Path):
        self.directory = directory
        self.manifest = read_json(directory / "frozen_manifest.json")
        self.expected = {row["runner_case_id"]: row for row in self.manifest["jobs"]}
        self.result_cache = {}
        self.last_refresh = None
        self.last_refresh_monotonic = float("-inf")

    def refresh_summary(self) -> None:
        self.last_refresh_monotonic = time.monotonic()
        started = now()
        try:
            completed = subprocess.run(
                [str(PYTHON), str(self.directory / "summarize_completion.py"),
                 "--run-dir", str(self.directory), "--output-dir", str(self.directory)],
                capture_output=True, text=True, timeout=60,
            )
            self.last_refresh = {"started_at_utc": started, "finished_at_utc": now(),
                                 "returncode": completed.returncode, "success": completed.returncode == 0}
            if completed.returncode:
                self.last_refresh["error_tail"] = completed.stderr[-2000:]
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.last_refresh = {"started_at_utc": started, "finished_at_utc": now(),
                                 "success": False, "error_type": type(exc).__name__}

    def result_snapshot(self) -> dict:
        observed = defaultdict(Counter)
        errors = []
        present = set()
        for path in (self.directory / "results").glob("*__lea.json"):
            present.add(path.name)
            case_id = path.name.removesuffix("__lea.json")
            if case_id not in self.expected:
                errors.append({"file": path.name, "reason": "outside_frozen_scope"})
                continue
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            cached = self.result_cache.get(path.name)
            if not cached or cached[0] != signature:
                try:
                    raw = read_json(path)
                    info = {"model": raw.get("model"), "case_id": raw.get("case_id"),
                            "completion_status": raw.get("completion_status")}
                    self.result_cache[path.name] = (signature, info)
                except (json.JSONDecodeError, AttributeError):
                    errors.append({"file": path.name, "reason": "unreadable_result"})
                    continue
            info = self.result_cache[path.name][1]
            expected = self.expected[case_id]
            if info["model"] != expected["model"] or info["case_id"] != case_id:
                errors.append({"file": path.name, "reason": "model_or_case_id_mismatch"})
                continue
            observed[info["model"]][info["completion_status"] or "unknown"] += 1
        for stale in set(self.result_cache) - present:
            del self.result_cache[stale]
        return {"observed_terminal_results": sum(sum(counts[status] for status in TERMINAL_RESULTS) for counts in observed.values()),
                "by_model": {model: dict(counts) for model, counts in observed.items()}, "errors": errors,
                "note": "Artifact counts are provisional; scientific coverage comes from the last identity-verified summary."}

    def snapshot(self) -> dict:
        launches = read_json(self.directory / "launched_processes.json", [])
        current, superseded = select_current_launches(launches)
        workers_by_pid = {}
        for path in (self.directory / "worker_status").glob("*.json"):
            raw = read_json(path, {})
            workers_by_pid[raw.get("pid")] = raw
        current_states = []
        for launch in current:
            status = {**launch, **inspect_process(launch)}
            worker = workers_by_pid.get(status["pid"], {})
            status["worker"] = {key: worker.get(key) for key in (
                "state", "updated_at", "active_case", "selected_cases", "completed_this_invocation",
                "skipped_terminal_cases", "blocked_models",
            )}
            current_states.append(status)
        # A superseded but genuinely live runner is a relevant anomaly; dead
        # smoke PIDs and reused process IDs never count as active workers.
        superseded_live = []
        for launch in superseded:
            checked = inspect_process(launch)
            if checked["alive"]:
                superseded_live.append({**launch, **checked})
        active = sum(row["alive"] for row in current_states) + len(superseded_live)
        verification = read_json(self.directory / "verification.json", {})
        budget = read_json(self.directory / "budget_status.json", {})
        results = self.result_snapshot()
        remaining = {model: count-sum(results["by_model"].get(model, {}).get(s, 0) for s in TERMINAL_RESULTS)
                     for model, count in self.manifest["missing_by_model"].items()}
        reasons = []
        if remaining.get("qwen2.5-72b", 0) and not any(row["model"] == "qwen2.5-72b" for row in current_states):
            reasons.append({"model": "qwen2.5-72b", "reason": "missing_openrouter_credentials_at_launch",
                            "required_env": "OPENROUTER_API_KEY", "remaining_cases": remaining["qwen2.5-72b"]})
        halt = read_json(self.directory / "budget_halt.json")
        if halt:
            reasons.append({"reason": "shared_budget_or_integrity_halt", "detail": halt})
        if results["errors"]:
            reasons.append({"reason": "result_artifact_anomaly", "details": results["errors"]})
        if verification and not verification.get("verification_passed"):
            reasons.append({"reason": "summary_identity_verification_failed"})
        if self.last_refresh and not self.last_refresh["success"]:
            reasons.append({"reason": "summary_refresh_failed"})
        if superseded_live:
            reasons.append({"reason": "superseded_runner_still_live", "pids": [row["pid"] for row in superseded_live]})
        if not active:
            for model, count in remaining.items():
                if count and model != "qwen2.5-72b":
                    reasons.append({"model": model, "reason": "workers_exited_with_remaining_cases", "remaining_cases": count})
            if not current_states:
                reasons.append({"reason": "no_supported_launch_records"})
        verified = {key: verification.get(key) for key in (
            "created_at_utc", "verification_passed", "completion_status", "available_lea_cells",
            "new_available_cells", "reused_available_cells", "missing_lea_cells", "status_counts",
        )}
        if not active and verification.get("missing_lea_cells", 320) > 0 and not reasons:
            reasons.append({"reason": "verified_scope_incomplete"})
        return {"updated_at_utc": now(), "monitor_pid": os.getpid(), "state": "running" if active else "needs_attention" if reasons else "finished",
                "read_only_monitor": True, "api_calls_by_monitor": 0, "active_processes": active,
                "all_observed_workers_exited": not bool(active), "current_launches": current_states,
                "superseded_live_launches": superseded_live, "ignored_old_launch_records": len(superseded)-len(superseded_live),
                "observed_results": results, "remaining_completion_jobs_by_model": remaining,
                "verified_coverage": verified, "budget": budget, "attention_reasons": reasons,
                "summary_refresh": self.last_refresh, "run_directory": str(self.directory)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=HERE)
    parser.add_argument("--poll-seconds", type=float, default=10)
    parser.add_argument("--summary-seconds", type=float, default=60)
    parser.add_argument("--once", action="store_true", help="Refresh summary and write one local snapshot, then exit.")
    args = parser.parse_args()
    if not PYTHON.is_file():
        parser.error(f"Required existing Python runtime not found: {PYTHON}")
    if not 1 <= args.poll_seconds <= 60 or args.summary_seconds < 1:
        parser.error("poll-seconds must be 1..60; summary-seconds must be positive")
    monitor = Monitor(args.run_dir.resolve())
    while True:
        state = monitor.snapshot()
        terminal = state["all_observed_workers_exited"]
        if args.once or terminal or time.monotonic()-monitor.last_refresh_monotonic >= args.summary_seconds:
            monitor.refresh_summary()
            # Re-read launch records after the refresh: a new real worker may
            # have started while a previous generation was finishing.
            state = monitor.snapshot()
            terminal = state["all_observed_workers_exited"]
        state["monitor_will_exit"] = bool(args.once or terminal)
        state["monitor_exit_reason"] = "once_snapshot" if args.once else "all_workers_exited" if terminal else None
        atomic_write(monitor.directory / "live_status.json", state)
        if args.once or terminal:
            print(json.dumps({"state": state["state"], "active_processes": state["active_processes"],
                              "verified_coverage": state["verified_coverage"], "remaining_jobs": state["remaining_completion_jobs_by_model"],
                              "summary_refresh": state["summary_refresh"]}, ensure_ascii=False, indent=2))
            return 0 if state.get("summary_refresh", {}).get("success") else 1
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
