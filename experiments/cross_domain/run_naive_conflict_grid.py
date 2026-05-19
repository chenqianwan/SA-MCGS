"""Case-level parallel launcher for structural memory-stress Naive calibration.

Each (template, domain, size, model) runs in its own subprocess. This keeps a
slow or stuck API call from blocking the rest of the grid.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
RESULTS_DIR = SCRIPT_DIR / "results"
LOG_DIR = RESULTS_DIR / "grid_logs"
SUMMARY_DIR = RESULTS_DIR / "grid_runs"


def _load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        env[key.strip()] = value
    return env


async def _run_case(case: dict, semaphore: asyncio.Semaphore, timeout: int) -> dict:
    async with semaphore:
        tag = (
            f"{case['template']}_{case['domain']}_{case['model']}_"
            f"{case['size']}_{int(time.time() * 1000)}"
        )
        safe_tag = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tag)
        log_path = LOG_DIR / f"{safe_tag}.log"
        result_glob = (
            f"battle_inject_memory_stress_{case['template']}_rankednaive_"
            f"naiveonly_{safe_tag}_*.json"
        )
        cmd = [
            sys.executable,
            "run_cross_domain_battle.py",
            "--inject",
            "--inject-profile",
            "memory_stress",
            "--conflict-template",
            case["template"],
            "--cycle-source",
            "synthetic_long",
            "--allow-synthetic-diagnostic",
            "--synthetic-sizes",
            str(case["size"]),
            "--domains",
            case["domain"],
            "--models",
            case["model"],
            "--max-sccs",
            "1",
            "--methods",
            "naive",
            "--naive-profile",
            "ranked",
            "--run-tag",
            safe_tag,
        ]
        env = os.environ.copy()
        env.update(_load_dotenv(REPO_ROOT / ".env"))

        started = time.time()
        with log_path.open("wb") as log:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=SCRIPT_DIR,
                env=env,
                stdout=log,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                return_code = await asyncio.wait_for(proc.wait(), timeout=timeout)
                status = "ok" if return_code == 0 else "error"
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return_code = None
                status = "timeout"

        result_files = sorted(RESULTS_DIR.glob(result_glob))
        return {
            **case,
            "status": status,
            "return_code": return_code,
            "seconds": round(time.time() - started, 2),
            "log": str(log_path),
            "result_files": [str(p) for p in result_files],
        }


async def _main(args: argparse.Namespace) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

    cases = [
        {"template": template, "domain": domain, "size": size, "model": model}
        for template in args.templates
        for domain in args.domains
        for size in args.sizes
        for model in args.models
    ]
    semaphore = asyncio.Semaphore(args.concurrency)
    print(
        f"Launching {len(cases)} Naive cases with concurrency={args.concurrency}, "
        f"timeout={args.case_timeout}s"
    )

    completed: list[dict] = []
    tasks = [
        asyncio.create_task(_run_case(case, semaphore, args.case_timeout))
        for case in cases
    ]
    for idx, task in enumerate(asyncio.as_completed(tasks), start=1):
        result = await task
        completed.append(result)
        print(
            f"[{idx}/{len(cases)}] {result['status']:<7} "
            f"{result['template']} {result['domain']} {result['size']} {result['model']} "
            f"{result['seconds']}s"
        )

    summary_path = SUMMARY_DIR / f"naive_conflict_grid_{int(time.time())}.json"
    summary_path.write_text(json.dumps(completed, indent=2))
    print(f"Summary saved: {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parallel Naive conflict-template grid runner")
    parser.add_argument(
        "--templates",
        nargs="+",
        default=["temporal_gate", "condition_trigger"],
    )
    parser.add_argument(
        "--domains",
        nargs="+",
        default=["debian", "wikipedia", "sec_ex21"],
    )
    parser.add_argument("--sizes", nargs="+", type=int, default=[5, 8, 12, 16, 24])
    parser.add_argument("--models", nargs="+", default=["gpt-4o", "deepseek-v3"])
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--case-timeout", type=int, default=420)
    asyncio.run(_main(parser.parse_args()))
