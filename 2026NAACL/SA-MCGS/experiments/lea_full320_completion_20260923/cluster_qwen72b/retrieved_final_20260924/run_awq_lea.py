#!/usr/bin/env python3
"""Validate a pinned local model, serve on loopback, run LEA, release the GPU.

The separate zero-GPU download job must finish successfully first. This program
does not download anything, modify the shared runtime, or edit frozen inputs.
"""
from __future__ import annotations

import argparse
import atexit
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import time
from urllib.request import urlopen

REPOSITORY = "Qwen/Qwen2.5-72B-Instruct-AWQ"
REVISION = "698703eae6604af048a3d2f509995dc302088217"
MODEL_ALIAS = "qwen2.5-72b-instruct"
BASE_URL = "http://127.0.0.1:18072/v1"
stop_requested = False
# Explicitly disable inherited project .env loading in every launched process.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_model(root: Path, marker_path: Path) -> dict:
    model = root / "model"
    official = json.loads((root / "official_model_metadata.json").read_text())
    marker = json.loads(marker_path.read_text())
    if (official.get("id") != REPOSITORY or official.get("sha") != REVISION
        or marker.get("repository") != REPOSITORY or marker.get("revision") != REVISION
        or marker.get("verified") is not True
        or Path(marker.get("model_path", "")).resolve() != model.resolve()):
        raise RuntimeError("Download marker does not identify the pinned verified checkpoint")
    expected = {f["rfilename"]: f for f in official["siblings"]}
    verified = {}
    for item in marker["files"]:
        raw = Path(item["path"])
        name = str(raw.relative_to(model)) if raw.is_absolute() else str(raw)
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise RuntimeError("Download marker contains an unsafe filename")
        if name in verified:
            raise RuntimeError("Duplicate file in download marker")
        verified[name] = item
    config = json.loads((model / "config.json").read_text())
    quant = config.get("quantization_config") or {}
    if (config.get("model_type") != "qwen2" or config.get("architectures") != ["Qwen2ForCausalLM"]
        or config.get("hidden_size") != 8192 or config.get("num_hidden_layers") != 80
        or config.get("intermediate_size") != 29696
        or config.get("torch_dtype", config.get("dtype")) != "float16"
        or quant.get("quant_method") != "awq" or quant.get("bits") != 4
        or quant.get("group_size") != 128 or quant.get("zero_point") is not True
        or str(quant.get("version", "")).lower() != "gemm"):
        raise RuntimeError("Model config does not match the official 72B AWQ checkpoint")
    index = json.loads((model / "model.safetensors.index.json").read_text())
    shards = sorted(set(index["weight_map"].values()))
    official_shards = sorted(n for n in expected if n.endswith(".safetensors"))
    if shards != official_shards or len(shards) != 11:
        raise RuntimeError("Checkpoint index is missing official weight shards")
    required = {"config.json", "model.safetensors.index.json", "tokenizer_config.json",
                "tokenizer.json", "generation_config.json", *shards}
    files = []
    for name in sorted(required):
        path = model / name
        metadata, checked = expected[name], verified[name]
        actual_size = path.stat().st_size
        if actual_size != metadata["size"] or actual_size != checked["size"]:
            raise RuntimeError(f"Checkpoint file size mismatch: {name}")
        if not checked.get("verification") or len(checked.get("sha256", "")) != 64:
            raise RuntimeError(f"Missing full-download verification: {name}")
        if metadata.get("lfs"):
            if checked["sha256"] != metadata["lfs"]["sha256"]:
                raise RuntimeError(f"Shard download checksum differs from official LFS: {name}")
        elif sha256(path) != checked["sha256"]:
            raise RuntimeError(f"Checkpoint metadata changed since download: {name}")
        files.append({"path": name, "size": actual_size, "sha256": checked["sha256"]})
    # Read only each shard's header, checking tensor locations against the index.
    # Full LFS SHA256 verification already happened without occupying a GPU.
    tensor_names = set()
    for name in shards:
        path = model / name
        with path.open("rb") as stream:
            header_size = struct.unpack("<Q", stream.read(8))[0]
            if not 0 < header_size < 64 * 1024 * 1024:
                raise RuntimeError(f"Invalid safetensors header size: {name}")
            header = json.loads(stream.read(header_size))
        payload_bytes = path.stat().st_size - 8 - header_size
        for tensor, description in header.items():
            if tensor == "__metadata__":
                continue
            start, end = description["data_offsets"]
            if not 0 <= start <= end <= payload_bytes or index["weight_map"].get(tensor) != name:
                raise RuntimeError(f"Invalid tensor offset/index mapping: {name}/{tensor}")
            if tensor in tensor_names:
                raise RuntimeError("Duplicate checkpoint tensor")
            tensor_names.add(tensor)
    if tensor_names != set(index["weight_map"]):
        raise RuntimeError("Shard headers do not cover the full checkpoint index")
    return {"repository": REPOSITORY, "revision": REVISION, "model_path": str(model),
        "quantization_config": quant, "activation_dtype": "float16", "files": files,
        "startup_verification": "marker+official sizes+small-file hashes+all shard headers/index",
        "download_marker_sha256": sha256(marker_path), "verified_at": now()}


class Children:
    def __init__(self, job_root: Path, deadline: float):
        self.job_root, self.deadline = job_root, deadline
        self.items = []
        self.server = None

    def spawn(self, name: str, command: list[str], cwd: Path):
        log = (self.job_root / f"{name}.log").open("ab", buffering=0)
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, env=os.environ.copy())
        finally:
            log.close()
        self.items.append((name, process))
        write_json(self.job_root / "child_processes.json", {"updated_at": now(), "children": [
            {"name": n, "pid": p.pid, "returncode": p.poll()} for n, p in self.items]})
        return process

    def check(self):
        if stop_requested:
            raise RuntimeError("Slurm signal received; preserving checkpoints and stopping child processes")
        if time.monotonic() >= self.deadline:
            raise RuntimeError("Coordinator deadline reached; preserving checkpoints before Slurm timeout")
        if self.server is not None and self.server.poll() is not None:
            raise RuntimeError(f"vLLM server exited with code {self.server.returncode}")

    def wait(self, processes):
        while True:
            self.check()
            codes = [p.poll() for p in processes]
            if any(code not in (None, 0) for code in codes):
                raise RuntimeError(f"Experiment subprocess failed: exit codes {codes}")
            if all(code == 0 for code in codes):
                return
            time.sleep(1)

    def cleanup(self):
        # Every child uses a new session. Never pkill or touch unrelated jobs.
        active = [p for _, p in reversed(self.items) if p.poll() is None]
        for process in active:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        until = time.monotonic() + 20
        while any(p.poll() is None for p in active) and time.monotonic() < until:
            time.sleep(0.25)
        for process in active:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass


def result_counts(output_dir: Path):
    rows = [json.loads(p.read_text()) for p in (output_dir / "results").glob("*__lea.json")]
    if any(row.get("model") != "qwen2.5-72b" for row in rows):
        raise RuntimeError("Unexpected model in local Qwen experiment output")
    return {"complete": sum(row.get("completion_status") == "complete" for row in rows),
            "strict_failures": sum(row.get("completion_status") == "strict_experiment_failure" for row in rows),
            "result_files": len(rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--download-marker", type=Path)
    args = parser.parse_args()
    root, job_root = args.root.resolve(), args.job_root.resolve()
    if root != Path("/aifs4su/hansirui_3rd/chenlong/q72awq_20260924") or root not in job_root.parents:
        raise RuntimeError("Unexpected service or job output directory")
    marker_path = args.download_marker or root / "model_download_complete.json"
    repository = root / "repo"
    output_dir = root / "results" / "lea_qwen80"
    if output_dir.resolve() != output_dir:
        raise RuntimeError("Experiment output path was redirected outside the dedicated directory")
    launcher = repository / "cluster_launcher.py"
    lock = (root / "service_and_experiment.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    children = Children(job_root, time.monotonic() + 3 * 3600 + 55 * 60)
    atexit.register(children.cleanup)

    def requested(signum, frame):
        global stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, requested)
    signal.signal(signal.SIGINT, requested)
    state = {"started_at": now(), "job_id": os.environ.get("SLURM_JOB_ID"),
             "output_dir": str(output_dir), "model_alias": MODEL_ALIAS, "status": "preflight"}

    def status(**fields):
        state.update(fields)
        state["updated_at"] = now()
        write_json(job_root / "status.json", state)
        print(json.dumps(state, ensure_ascii=False), flush=True)

    try:
        status()
        if not launcher.is_file():
            raise RuntimeError("Staged experiment launcher is missing")
        write_json(job_root / "checkpoint_verified.json", verify_model(root, marker_path))
        import torch
        if torch.cuda.device_count() != 1:
            raise RuntimeError("Expected one Slurm-visible GPU")
        gpu_name = torch.cuda.get_device_name(0)
        memory = torch.cuda.get_device_properties(0).total_memory
        if "H800" not in gpu_name or memory < 75 * 1024**3:
            raise RuntimeError(f"Expected H800 80GB, received {gpu_name}")
        write_json(job_root / "runtime.json", {"gpu_name": gpu_name, "gpu_memory_bytes": memory,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "vllm_version": importlib.metadata.version("vllm"), "torch_version": torch.__version__,
            "transformers_version": importlib.metadata.version("transformers"), "hostname": socket.gethostname()})
        common = [sys.executable, "-B", str(launcher), "--output-dir", str(output_dir), "--base-url", BASE_URL]
        preflight = children.spawn("experiment_preflight", [*common, "--mode", "preflight"], repository)
        children.wait([preflight])
        tokenize = children.spawn("tokenizer_preflight", [*common, "--mode", "tokenize",
            "--tokenizer-path", str(root / "model"), "--max-model-len", "16384",
            "--max-output-tokens", "2048"], repository)
        children.wait([tokenize])
        children.check()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 18072))
        server_args = [sys.executable, "-B", "-m", "vllm.entrypoints.openai.api_server",
            "--model", str(root / "model"), "--served-model-name", MODEL_ALIAS,
            "--host", "127.0.0.1", "--port", "18072", "--dtype", "float16", "--quantization", "awq",
            "--tensor-parallel-size", "1", "--max-model-len", "16384", "--max-num-seqs", "4",
            "--gpu-memory-utilization", "0.90", "--generation-config", "vllm",
            "--override-generation-config", '{"top_k":-1,"top_p":1.0,"repetition_penalty":1.0}',
            "--enforce-eager", "--no-async-scheduling"]
        write_json(job_root / "server_command.json", {"argv": server_args, "base_url": BASE_URL})
        children.server = children.spawn("vllm_server", server_args, root)
        status(status="server_starting", server_pid=children.server.pid)
        start_deadline = time.monotonic() + 1800
        while True:
            children.check()
            if time.monotonic() >= start_deadline:
                raise RuntimeError("vLLM startup did not become healthy within 30 minutes")
            try:
                with urlopen(BASE_URL + "/models", timeout=5) as response:
                    models = json.load(response)
                if [row.get("id") for row in models.get("data", [])] != [MODEL_ALIAS]:
                    raise RuntimeError("Local endpoint returned an unexpected served model ID")
                write_json(job_root / "healthy_models.json", models)
                break
            except (OSError, ValueError):
                time.sleep(2)
        status(status="smoke")
        smoke = children.spawn("smoke_case20", [*common, "--mode", "smoke", "--smoke-case-order", "20"], repository)
        children.wait([smoke])
        plan = json.loads((output_dir / "case_plan.json").read_text())
        smoke_case = [case for case in plan if int(case.get("main_case_order", -1)) == 20]
        if len(smoke_case) != 1:
            raise RuntimeError("Fixed smoke case 20 is not unique")
        smoke_result = json.loads((output_dir / "results" / f"{smoke_case[0]['case_id']}__lea.json").read_text())
        if smoke_result.get("completion_status") != "complete":
            raise RuntimeError("Smoke case failed; bulk experiment was not started")
        status(status="running_four_shards", **result_counts(output_dir))
        workers = [children.spawn(f"lea_shard_{index}", [*common, "--mode", "run",
            "--shard-count", "4", "--shard-index", str(index)], repository) for index in range(4)]
        children.wait(workers)
        counts = result_counts(output_dir)
        if counts != {"complete": 80, "strict_failures": 0, "result_files": 80}:
            raise RuntimeError(f"LEA stopped without 80 complete cases: {counts}")
        status(status="complete", **counts)
        return 0
    except Exception as exc:
        status(status="failed_or_paused", error_type=type(exc).__name__, error=str(exc))
        return 1
    finally:
        children.cleanup()
        atexit.unregister(children.cleanup)
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
