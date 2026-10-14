#!/usr/bin/env python3
"""Submit the staged, authorized one-GPU job with a durable remote receipt."""
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent

CODE = r'''
import fcntl, hashlib, json, os, pathlib, subprocess, time
root = pathlib.Path("/aifs4su/hansirui_3rd/chenlong/llama8b_20260924")
if os.getuid() != 1083 or root.resolve() != root or root.stat().st_uid != os.getuid():
    raise SystemExit("Unexpected deployment root or account")
os.umask(0o077)
env = dict(os.environ, SLURM_CONF="/cm/shared/apps/slurm/var/etc/slurm/slurm.conf")
slurm = pathlib.Path("/cm/shared/apps/slurm/current/bin")
with (root / "gpu_submission.lock").open("a+") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    receipt = root / "gpu_submission.json"
    if receipt.exists():
        record = json.loads(receipt.read_text())
    else:
        marker_path = root / "model_download_complete.json"
        marker = json.loads(marker_path.read_text()) if marker_path.exists() else {}
        dependency = None
        prep = subprocess.run([str(slurm / "scontrol"), "show", "job", "394900", "-o"], env=env, text=True, capture_output=True)
        if not prep.returncode:
            fields = dict(part.split("=", 1) for part in prep.stdout.split() if "=" in part)
            if fields.get("JobName") != "chenlong_llama8b_prepare" or not fields.get("UserId", "").endswith("(1083)"):
                raise SystemExit("Unexpected prerequisite job identity")
            if fields.get("JobState") in {"PENDING", "RUNNING", "COMPLETING"}:
                dependency = "afterok:394900"
            elif fields.get("JobState") != "COMPLETED" or fields.get("ExitCode") != "0:0":
                raise SystemExit("Model preparation failed; GPU job not submitted")
        if dependency is None and (marker.get("verified") is not True or marker.get("state") != "complete"
                or marker.get("revision") != "0e9e39f249a16976918f6564b8830bc894c89659"):
            raise SystemExit("Checkpoint has not completed verification and has no active prerequisite")
        staging = json.loads((root / "gpu_staging_manifest.json").read_text())
        for relative, expected in staging["files"].items():
            path = root / relative
            if path.stat().st_size != expected["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
                raise SystemExit("Staged file changed: " + relative)
        command = [str(slurm / "sbatch"), "--parsable", "--comment=chenlong_llama8b_20260924"]
        if dependency:
            command.append("--dependency=" + dependency)
        command.append(str(root / "run_llama_experiment.sbatch"))
        # Validate current partition/QOS limits without allocating any resource.
        check = subprocess.run([*command[:-1], "--test-only", command[-1]], env=env, text=True, capture_output=True)
        if check.returncode:
            raise SystemExit("Slurm pre-submission check rejected: " + check.stderr)
        # A durable intent blocks an ambiguous retry after sbatch accepted a job.
        intent = root / "gpu_submission_intent.json"
        if intent.exists():
            raise SystemExit("Unresolved prior submission intent; inspect our queue before retrying")
        intent.write_text(json.dumps({"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "job_name": "chenlong_llama8b_3methods"}) + "\n")
        result = subprocess.run(command, env=env, text=True, capture_output=True)
        if result.returncode:
            (root / "gpu_submission_failure.json").write_text(json.dumps({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}) + "\n")
            raise SystemExit(result.stderr)
        job_id = result.stdout.strip().split(";")[0]
        if not job_id.isdigit():
            raise SystemExit("Unrecognized sbatch reply; inspect our queue before retrying: " + result.stdout)
        record = {"job_id": job_id, "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "download_job_id": "394900", "dependency": dependency, "download_prerequisite": "after successful CPU preparation; pinned checkpoint hash reverified by GPU coordinator", "root": str(root), "gpu_count": 1, "cpus": 16, "memory": "128G", "time_limit": "5-00:00:00", "nodes": 1, "cases": 80, "methods": ["naive-single", "lea", "sa-mcgs"], "expected_results": 240, "external_api_spend_usd": 0, "staging_manifest_sha256": hashlib.sha256((root / "gpu_staging_manifest.json").read_bytes()).hexdigest(), "sbatch_argv": command, "sbatch_stdout": result.stdout, "sbatch_stderr": result.stderr}
        receipt.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)
    subprocess.run([str(slurm / "scontrol"), "show", "job", record["job_id"]], env=env, check=True)
'''


if __name__ == "__main__":
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", "Group3_slogin", "/usr/bin/python3 -B -c " + shlex.quote(CODE)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    output = result.stdout + result.stderr
    (HERE / "gpu_submission_receipt.txt").write_text(output)
    print(output, end="")
    raise SystemExit(result.returncode)
