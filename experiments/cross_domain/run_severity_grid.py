#!/usr/bin/env python3
"""Run memory-stress severity sweeps with bounded process-level parallelism.

Each subprocess runs one domain/size/template/severity block with both models
and both methods. The underlying battle script checkpoints its own JSON output;
this wrapper adds coarse progress/status files and per-task logs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "experiments" / "cross_domain" / "results"
LOG_DIR = RESULTS_DIR / "severity_grid_logs"

DEFAULT_DOMAIN_SIZES = {
    "bgb": [14, 25],
    "cuad": [18, 25],
}
DEFAULT_TEMPLATES = [
    "direct_mutex",
    "handoff_invariant",
    "temporal_gate",
    "condition_trigger",
]
DEFAULT_SEVERITIES = ["standard", "severe", "critical"]
DEFAULT_MODELS = ["gpt-4o", "deepseek-v3"]
DEFAULT_METHODS = ["naive", "sa-mcgs"]
DEFAULT_COMPRESSION_PROFILES = ["current"]


@dataclass
class Task:
    task_id: int
    domain: str
    size: int
    template: str
    severity: str
    compression_profile: str
    run_tag: str
    log_path: str
    status: str = "pending"
    attempt: int = 0
    returncode: int | None = None
    result_file: str | None = None
    started_at: float | None = None
    ended_at: float | None = None


def parse_domain_sizes(values: list[str] | None) -> dict[str, list[int]]:
    if not values:
        return {k: list(v) for k, v in DEFAULT_DOMAIN_SIZES.items()}
    parsed: dict[str, list[int]] = {}
    for raw in values:
        if ":" not in raw:
            raise ValueError(f"Invalid domain size spec: {raw}")
        domain, sizes_raw = raw.split(":", 1)
        sizes: list[int] = []
        for chunk in sizes_raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "-" in chunk:
                left, right = chunk.split("-", 1)
                sizes.extend(range(int(left), int(right) + 1))
            else:
                sizes.append(int(chunk))
        parsed[domain.strip()] = sorted(set(sizes))
    return parsed


def safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def build_tasks(args: argparse.Namespace) -> list[Task]:
    domain_sizes = parse_domain_sizes(args.domain_sizes)
    tasks: list[Task] = []
    task_id = 0
    for domain in args.domains:
        for size in domain_sizes.get(domain, []):
            for template in args.templates:
                for severity in args.severities:
                    for compression_profile in args.mcgs_compression_profiles:
                        task_id += 1
                        tag = safe_token(
                            f"{args.run_tag}_{compression_profile}_{domain}{size}_"
                            f"{template}_{severity}_b{args.budget}"
                        )
                        log_path = LOG_DIR / f"{task_id:03d}_{tag}.log"
                        tasks.append(
                            Task(
                                task_id=task_id,
                                domain=domain,
                                size=size,
                                template=template,
                                severity=severity,
                                compression_profile=compression_profile,
                                run_tag=tag,
                                log_path=str(log_path),
                            )
                        )
    return tasks


def command_for(task: Task, args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "experiments/cross_domain/run_cross_domain_battle.py",
        "--domains",
        task.domain,
        "--models",
        *args.models,
        "--methods",
        *args.methods,
        "--inject",
        "--inject-profile",
        "memory_stress",
        "--conflict-template",
        task.template,
        "--conflict-severity",
        task.severity,
        "--cycle-source",
        "real_long",
        "--domain-size-ranges",
        f"{task.domain}:{task.size}",
        "--max-sccs",
        "1",
        "--mcgs-budget",
        str(args.budget),
        "--mcgs-concurrency",
        str(args.inner_concurrency),
        "--mcgs-compression-profile",
        task.compression_profile,
        "--include-subgraph-summary",
        "--mcgs-trace",
        "--naive-profile",
        "direct_subgraph",
        "--run-tag",
        task.run_tag,
    ]


def write_status(path: Path, tasks: list[Task]) -> None:
    summary: dict[str, int] = {}
    for task in tasks:
        summary[task.status] = summary.get(task.status, 0) + 1
    payload = {
        "updated_at": time.time(),
        "summary": summary,
        "tasks": [asdict(task) for task in tasks],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def run_task(
    task: Task,
    args: argparse.Namespace,
    semaphore: asyncio.Semaphore,
    status_path: Path,
    status_lock: asyncio.Lock,
    tasks: list[Task],
) -> None:
    async with semaphore:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        command = command_for(task, args)
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        for attempt in range(1, args.retries + 2):
            task.attempt = attempt
            task.started_at = time.time()
            task.ended_at = None
            task.returncode = None
            task.result_file = None
            task.status = "running"
            async with status_lock:
                write_status(status_path, tasks)
            print(
                f"[{task.task_id:03d}/{len(tasks):03d}] start attempt {attempt}: "
                f"{task.domain} {task.size} {task.template} {task.severity} "
                f"{task.compression_profile}",
                flush=True,
            )

            result_file = None
            with open(task.log_path, "a", encoding="utf-8") as log:
                log.write("\n" + "=" * 80 + "\n")
                log.write(" ".join(command) + "\n")
                log.flush()
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(ROOT),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                assert proc.stdout is not None
                async for raw in proc.stdout:
                    text = raw.decode("utf-8", errors="replace")
                    log.write(text)
                    if "Results saved:" in text:
                        result_file = text.split("Results saved:", 1)[1].strip()
                returncode = await proc.wait()
                log.write(f"\n[returncode] {returncode}\n")

            task.returncode = returncode
            task.result_file = result_file
            task.ended_at = time.time()
            if returncode == 0:
                task.status = "done"
                print(
                    f"[{task.task_id:03d}/{len(tasks):03d}] done: "
                    f"{task.domain} {task.size} {task.template} {task.severity} "
                    f"{task.compression_profile}",
                    flush=True,
                )
                async with status_lock:
                    write_status(status_path, tasks)
                return

            task.status = "retrying" if attempt <= args.retries else "failed"
            async with status_lock:
                write_status(status_path, tasks)
            print(
                f"[{task.task_id:03d}/{len(tasks):03d}] returncode={returncode}; "
                f"status={task.status}; log={task.log_path}",
                flush=True,
            )
            if attempt <= args.retries:
                await asyncio.sleep(args.retry_sleep)


async def main_async(args: argparse.Namespace) -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(args)
    status_path = RESULTS_DIR / f"{safe_token(args.run_tag)}_severity_grid_status.json"
    write_status(status_path, tasks)
    print(f"Severity grid tasks: {len(tasks)}")
    print(f"Status file: {status_path}")
    print(f"Log dir: {LOG_DIR}")

    semaphore = asyncio.Semaphore(args.outer_concurrency)
    status_lock = asyncio.Lock()
    await asyncio.gather(
        *[
            run_task(task, args, semaphore, status_path, status_lock, tasks)
            for task in tasks
        ]
    )
    write_status(status_path, tasks)
    failed = [task for task in tasks if task.status != "done"]
    if failed:
        print(f"Failed tasks: {len(failed)}")
        for task in failed:
            print(
                f"  - {task.task_id}: {task.domain} {task.size} "
                f"{task.template} {task.severity} {task.compression_profile}"
            )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run structural-severity grid experiments.")
    parser.add_argument("--domains", nargs="+", default=["cuad", "bgb"])
    parser.add_argument("--domain-sizes", nargs="*", help="Specs such as 'cuad:18,25' or 'bgb:14-25'.")
    parser.add_argument("--templates", nargs="+", default=DEFAULT_TEMPLATES)
    parser.add_argument("--severities", nargs="+", default=DEFAULT_SEVERITIES)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--methods", nargs="+", choices=DEFAULT_METHODS, default=DEFAULT_METHODS)
    parser.add_argument(
        "--mcgs-compression-profiles",
        nargs="+",
        choices=["current", "conservative", "balanced", "aggressive"],
        default=DEFAULT_COMPRESSION_PROFILES,
    )
    parser.add_argument("--budget", type=int, default=60)
    parser.add_argument("--inner-concurrency", type=int, default=8)
    parser.add_argument("--outer-concurrency", type=int, default=6)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--retry-sleep", type=float, default=10.0)
    parser.add_argument("--run-tag", default="severitygrid_2case")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
