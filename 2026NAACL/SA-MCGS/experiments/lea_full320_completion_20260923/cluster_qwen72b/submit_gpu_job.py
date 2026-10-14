#!/usr/bin/env python3
"""Submit the staged, authorized one-GPU job with a durable remote receipt."""
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent

CODE = r'''
import fcntl, hashlib, json, os, pathlib, subprocess, time
root = pathlib.Path("/aifs4su/hansirui_3rd/chenlong/q72awq_20260924")
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
        marker = json.loads((root / "model_download_complete.json").read_text())
        if marker.get("verified") is not True or marker.get("state") != "complete":
            raise SystemExit("Checkpoint has not completed verification")
        staging = json.loads((root / "gpu_staging_manifest.json").read_text())
        for relative, expected in staging["files"].items():
            path = root / relative
            if path.stat().st_size != expected["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
                raise SystemExit("Staged file changed: " + relative)
        # A durable intent blocks an ambiguous retry after sbatch accepted a job.
        intent = root / "gpu_submission_intent.json"
        if intent.exists():
            raise SystemExit("Unresolved prior submission intent; inspect our queue before retrying")
        intent.write_text(json.dumps({"created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "job_name": "chenlong_qwen72_lea80"}) + "\n")
        # The download has already completed and its output is fully verified.
        # Finished short jobs can age out of Slurm's dependency lookup quickly.
        command = [str(slurm / "sbatch"), "--parsable", "--comment=chenlong_q72awq_20260924", str(root / "run_awq_lea.sbatch")]
        result = subprocess.run(command, env=env, text=True, capture_output=True)
        if result.returncode:
            (root / "gpu_submission_failure.json").write_text(json.dumps({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}) + "\n")
            raise SystemExit(result.stderr)
        job_id = result.stdout.strip().split(";")[0]
        if not job_id.isdigit():
            raise SystemExit("Unrecognized sbatch reply; inspect our queue before retrying: " + result.stdout)
        record = {"job_id": job_id, "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "download_job_id": "394276", "dependency": None, "download_prerequisite": "already completed; verified completion marker and checkpoint", "root": str(root), "gpu_count": 1, "cpus": 16, "memory": "128G", "time_limit": "04:00:00", "cases": 80, "external_api_spend_usd": 0, "staging_manifest_sha256": hashlib.sha256((root / "gpu_staging_manifest.json").read_bytes()).hexdigest(), "sbatch_stdout": result.stdout, "sbatch_stderr": result.stderr}
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
