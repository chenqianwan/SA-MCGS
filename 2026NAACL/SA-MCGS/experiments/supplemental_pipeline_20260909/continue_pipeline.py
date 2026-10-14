#!/usr/bin/env python3
"""Continue the active cost run into the frozen prior fallback; no scheduler.

Never restarts cost, retries an invalid case, expands scope, or supplies labels.
The prior runner remains the authority for identities, ordering and USD 200.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
REPO = PROJECT.parents[1]
COST = PROJECT / "experiments/cost_prior_12case_gpt4o_gemini25pro_b60_v1"
PRIOR = PROJECT / "experiments/prior_fallback_slots_01_03_08_10"
RUNNER = PRIOR / "run_prior_fallback.py"
PYTHON = "/opt/homebrew/anaconda3/bin/python"
BALANCE_FLOOR = 707.078988


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load(path):
    return json.loads(path.read_text())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def state(name, **details):
    item = {"updated_at": now(), "state": name, "pid": os.getpid(),
            "budget_ceiling_usd": 200, "expert_results": "awaiting_author_labels", **details}
    save(HERE / "execution_status.json", item)
    print(json.dumps(item, ensure_ascii=False), flush=True)


def run_cli(*arguments):
    with (HERE / "runner.log").open("a") as log:
        subprocess.run([PYTHON, str(RUNNER), *arguments], cwd=REPO,
                       stdout=log, stderr=subprocess.STDOUT, check=True)


def run_closeout():
    output = HERE / "clustered_closeout"
    with (HERE / "runner.log").open("a") as log:
        subprocess.run([PYTHON, str(COST / "paired_cluster_closeout.py"),
                        "--cost-dir", str(COST), "--prior-dir", str(PRIOR),
                        "--out-dir", str(output)], cwd=REPO,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    return str(output)


def cost_ready(payload):
    cells = payload.get("cells", {}).get("cost", {})
    return (payload.get("state") == "cost_complete" and cells.get("attempted") == 72
            # The frozen runner serializes Counter: zero-valued categories
            # can be absent. The 72 terminal + valid/invalid checks still bind.
            and cells.get("missing", 0) == 0
            and cells.get("valid", 0) + cells.get("invalid", 0) == 72)


def matching_cost_process(pid):
    response = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "command="],
                              capture_output=True, text=True)
    return response.returncode == 0 and (
        "run_cost_prior.py cost" in response.stdout or
        (str(HERE / "resume_cost_after_interruption.py") in response.stdout
         and "--execute" in response.stdout)
    )


def wait_for_cost(pid):
    previous = None
    while True:
        payload = load(COST / "execution_status.json")
        alive = matching_cost_process(pid)
        if cost_ready(payload) and not alive:
            state("cost_complete_verified_by_status", cells=payload["cells"]["cost"])
            return
        if not alive:
            raise RuntimeError("Cost process exited without a complete 72-cell terminal state; no automatic rerun")
        signature = (payload.get("state"), json.dumps(payload.get("cells")))
        if signature != previous:
            state("waiting_for_active_cost", cost_pid=pid,
                  cells=payload.get("cells", {}).get("cost"), current=payload.get("current"))
            previous = signature
        time.sleep(30)


def capture_balance():
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env", override=False)
    key = os.environ.get("XHUB_API_KEY")
    if not key:
        raise RuntimeError("Missing XHub credential; no paid launch")
    req = urllib.request.Request("https://api3.xhub.chat/api/usage/token/",
                                 headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as response:
        usage = json.load(response)
    with urllib.request.urlopen("https://api3.xhub.chat/api/status", timeout=30) as response:
        provider_status = json.load(response)
    divisor = float(provider_status["data"]["quota_per_unit"])
    if divisor <= 0:
        raise RuntimeError("Invalid XHub quota conversion")
    snapshot = {"schema_version": "xhub_balance_snapshot.v1", "context_kind": "authoritative",
                "provider": "XHub", "source": "coordinator_captured_account_balance",
                "captured_by": "sa-mcgs-local-cost-fallback-pipeline",
                "authorization_scope_id": "sa-mcgs-arr-oct2026-global-200-v1",
                "captured_at": now(),
                "total_available_usd": float(usage["data"]["total_available"]) / divisor,
                "quota_per_unit": divisor}
    path = HERE / "balance_snapshots" / f"balance_{time.time_ns()}.json"
    save(path, snapshot)
    return path, snapshot


def continue_prior():
    while True:
        run_cli("preflight")
        gate = load(PRIOR / "preflight/gate.json")
        if not gate["intrinsic_ready"]:
            raise RuntimeError("Prior identity/parent/protocol gate failed; inspect preflight/gate.json")
        if gate["already_complete"]:
            run_cli("report")
            closeout = run_closeout()
            state("paid_experiments_complete_labels_pending",
                  prior_cells=gate["local_result_state"],
                  attributable_spend_usd=gate["accounting_provenance"]["validated_cumulative_spend_usd"],
                  cost_report=str(COST / "REPORT_ZH.md"), prior_report=str(PRIOR / "REPORT_ZH.md"),
                  paired_clustered_statistics=closeout)
            return
        remaining = float(gate["accounting_provenance"]["derived_authorization_remaining_usd"])
        path, snapshot = capture_balance()
        snapshot_hash = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        shared_room = snapshot["total_available_usd"] - BALANCE_FLOOR
        arguments = ["--global-authorization-usd", "200",
                     "--global-authorization-remaining-usd", str(remaining),
                     "--closeout-reserve-usd", "10",
                     "--accounting-context-kind", "authoritative",
                     "--fresh-xhub-balance-usd", str(snapshot["total_available_usd"]),
                     "--fresh-balance-captured-at", snapshot["captured_at"],
                     "--fresh-balance-snapshot", str(path),
                     "--fresh-balance-snapshot-sha256", snapshot_hash]
        run_cli("dry-run", *arguments)
        launch = load(PRIOR / "preflight/gate.json")
        if not launch["ready_for_paid_run"]:
            raise RuntimeError("Fresh launch budget/parity gate closed; no paid call made")
        required = float(launch["budget_gate"]["required_including_closeout_usd"])
        if required > shared_room:
            raise RuntimeError("Shared-account cross-check cannot cover the frozen tail plus reserve")
        state("running_prior_fallback", next_order=launch["local_result_state"]["next_order"],
              remaining_authorized_usd=remaining, account_available_usd=snapshot["total_available_usd"],
              required_tail_including_reserve_usd=required)
        # One terminal cell per invocation allows fresh balance/ledger checks
        # between long Gemini calls. Valid and invalid results are both retained.
        run_cli("run", *arguments, "--execute-paid-cells", "--max-new-cells", "1")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cost-pid", type=int, default=94022)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "inspect_only_no_network_no_paid_calls",
                          "cost": load(COST / "execution_status.json"),
                          "prior_runner": str(RUNNER)}, ensure_ascii=False, indent=2))
        return
    with (HERE / "pipeline.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())])
        try:
            wait_for_cost(args.cost_pid)
            continue_prior()
        except Exception as exc:
            state("stopped_requires_review", error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            awake.terminate()


if __name__ == "__main__":
    main()
