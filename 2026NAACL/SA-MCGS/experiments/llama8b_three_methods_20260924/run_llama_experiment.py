#!/usr/bin/env python3
"""One allocated H800 hosts the pinned Llama model and all three methods.

This coordinator never downloads weights or uses external inference endpoints.
Only its own process groups are terminated on completion or interruption.
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

REPOSITORY = "meta-llama/Llama-3.1-8B-Instruct"
REVISION = "0e9e39f249a16976918f6564b8830bc894c89659"
MODEL_ALIAS = "llama-3.1-8b-instruct"
PORT = 18081
BASE_URL = f"http://127.0.0.1:{PORT}/v1"
METHODS = ("naive-single", "lea", "sa-mcgs")
TERMINAL = {"complete", "strict_experiment_failure"}
stop_requested = False
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_staging(root):
    manifest = read(root / "gpu_staging_manifest.json")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Unsafe staged relative path")
        path = root / relative
        if path.resolve() != path or path.stat().st_size != expected["bytes"] or digest(path) != expected["sha256"]:
            raise RuntimeError("Staged input changed: " + name)
    return {"sha256": digest(root / "gpu_staging_manifest.json"), "files": len(manifest["files"])}


def verify_model(root):
    model = root / "models/llama-3.1-8b-instruct"
    official = read(root / "official_model_metadata.json")
    marker_path = root / "model_download_complete.json"
    marker = read(marker_path)
    if (official.get("id") != REPOSITORY or official.get("sha") != REVISION
            or marker.get("repository") != REPOSITORY or marker.get("revision") != REVISION
            or marker.get("verified") is not True or marker.get("state") != "complete"
            or Path(marker["model_path"]).resolve() != model.resolve()):
        raise RuntimeError("Expected a verified complete download of the pinned Meta checkpoint")
    expected = {row["rfilename"]: row for row in official["siblings"]}
    verified = {}
    for row in marker["files"]:
        p = Path(row["path"])
        name = str(p.relative_to(model)) if p.is_absolute() else str(p)
        if name in verified or Path(name).is_absolute() or ".." in Path(name).parts:
            raise RuntimeError("Invalid or duplicate model marker entry")
        verified[name] = row
    config = read(model / "config.json")
    if (config.get("architectures") != ["LlamaForCausalLM"] or config.get("model_type") != "llama"
            or config.get("hidden_size") != 4096 or config.get("num_hidden_layers") != 32
            or config.get("num_attention_heads") != 32 or config.get("num_key_value_heads") != 8
            or config.get("torch_dtype", config.get("dtype")) != "bfloat16"
            or config.get("quantization_config")):
        raise RuntimeError("Checkpoint is not the expected original BF16 Llama 3.1 8B")
    index = read(model / "model.safetensors.index.json")
    shards = sorted(set(index["weight_map"].values()))
    if shards != sorted(n for n in expected if n.endswith(".safetensors")) or len(shards) != 4:
        raise RuntimeError("Model shard index does not cover all four official shards")
    required = {"config.json", "generation_config.json", "tokenizer.json", "tokenizer_config.json",
                "model.safetensors.index.json", *shards}
    files = []
    for name in sorted(required):
        p, metadata, checked = model / name, expected[name], verified[name]
        if p.resolve() != p or p.stat().st_size != metadata["size"] or p.stat().st_size != checked["size"]:
            raise RuntimeError("Checkpoint file size/path mismatch: " + name)
        actual = digest(p)
        if actual != checked["sha256"]:
            raise RuntimeError("Checkpoint content changed since download: " + name)
        if metadata.get("lfs") and actual != metadata["lfs"]["sha256"]:
            raise RuntimeError("Checkpoint differs from official LFS SHA256: " + name)
        if not metadata.get("lfs"):
            content = p.read_bytes()
            blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            if blob != metadata["blobId"]:
                raise RuntimeError("Metadata differs from official git blob: " + name)
        files.append({"path": name, "size": p.stat().st_size, "sha256": actual})
    tensor_names = set()
    for name in shards:
        p = model / name
        with p.open("rb") as stream:
            size = struct.unpack("<Q", stream.read(8))[0]
            if not 0 < size < 64 * 1024 * 1024:
                raise RuntimeError("Invalid safetensors header")
            header = json.loads(stream.read(size))
        payload_size = p.stat().st_size - size - 8
        for tensor, info in header.items():
            if tensor == "__metadata__":
                continue
            start, end = info["data_offsets"]
            if tensor in tensor_names or index["weight_map"].get(tensor) != name or not 0 <= start <= end <= payload_size:
                raise RuntimeError("Safetensors index/offset mismatch")
            tensor_names.add(tensor)
    if tensor_names != set(index["weight_map"]):
        raise RuntimeError("Incomplete checkpoint tensor coverage")
    return {"repository": REPOSITORY, "revision": REVISION, "model_path": str(model),
            "dtype": "bfloat16", "files": files, "marker_sha256": digest(marker_path), "verified_at": now()}


def counts(output):
    result = {method: {"complete": 0, "strict_experiment_failure": 0, "other": 0} for method in METHODS}
    for method in METHODS:
        for p in (output / "results").glob(f"*__{method}.json"):
            state = read(p).get("completion_status")
            result[method][state if state in TERMINAL else "other"] += 1
    return result


class Children:
    def __init__(self, job_root, deadline):
        self.root, self.deadline = job_root, deadline
        self.items, self.server = [], None

    def spawn(self, name, command, cwd):
        with (self.root / f"{name}.log").open("ab", buffering=0) as log:
            process = subprocess.Popen(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                       env=os.environ.copy(), start_new_session=True)
        self.items.append((name, process))
        write(self.root / "child_processes.json", {"at": now(), "children": [
            {"name": n, "pid": p.pid, "returncode": p.poll()} for n, p in self.items]})
        return process

    def check(self):
        if stop_requested or time.monotonic() >= self.deadline:
            raise RuntimeError("Job stopping: preserve checkpoints and release own processes")
        if self.server is not None and self.server.poll() is not None:
            raise RuntimeError("Local model server exited: " + str(self.server.returncode))

    def wait(self, processes, progress=None):
        last = 0
        while True:
            self.check()
            codes = [p.poll() for p in processes]
            if any(code not in (None, 0) for code in codes):
                raise RuntimeError("Experiment subprocess stopped: " + str(codes))
            if all(code == 0 for code in codes):
                return
            if progress and time.monotonic() - last >= 30:
                progress()
                last = time.monotonic()
            time.sleep(1)

    def cleanup(self):
        active = [p for _, p in reversed(self.items) if p.poll() is None]
        for p in active:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        until = time.monotonic() + 25
        while any(p.poll() is None for p in active) and time.monotonic() < until:
            time.sleep(0.25)
        for p in active:
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            p.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--job-time-limit-seconds", type=int, default=432000)
    parser.add_argument("--max-model-len", type=int, default=131072)
    args = parser.parse_args()
    root, job_root = args.root.resolve(), args.job_root.resolve()
    if not os.environ.get("SLURM_JOB_ID", "").isdigit() or root not in job_root.parents:
        raise RuntimeError("An allocated Slurm job with a personal output root is required")
    runner = root / "runner/llama_launcher.py"
    output = root / "results/llama80_three_methods"
    (root / "locks").mkdir(parents=True, exist_ok=True)
    lock = (root / "locks/coordinator.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    children = Children(job_root, time.monotonic() + args.job_time_limit_seconds - 600)
    atexit.register(children.cleanup)
    def requested(signum, frame):
        global stop_requested
        stop_requested = True
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGUSR1):
        signal.signal(signum, requested)
    state = {"started_at": now(), "job_id": os.environ["SLURM_JOB_ID"], "model": MODEL_ALIAS,
             "cases": 80, "methods": list(METHODS), "expected_results": 240,
             "time_limit_seconds": args.job_time_limit_seconds, "external_api_spend_usd": 0}
    def status(**fields):
        state.update(fields)
        state["updated_at"] = now()
        write(job_root / "status.json", state)
        print(json.dumps(state, ensure_ascii=False), flush=True)
    try:
        status(status="preflight")
        write(job_root / "staging_verified.json", verify_staging(root))
        common = [sys.executable, "-B", str(runner), "--output-dir", str(output),
                  "--base-url", BASE_URL, "--checkpoint-revision", REVISION,
                  "--max-model-len", str(args.max_model_len), "--case-concurrency", "2",
                  "--tokenizer-path", str(root / "models/llama-3.1-8b-instruct")]
        children.wait([children.spawn("experiment_preflight", [*common, "--mode", "preflight"], runner.parent)])
        write(job_root / "checkpoint_verified.json", verify_model(root))
        import torch
        if torch.cuda.device_count() != 1:
            raise RuntimeError("Exactly one Slurm-visible GPU is required")
        gpu = torch.cuda.get_device_name(0)
        total = torch.cuda.get_device_properties(0).total_memory
        free, _ = torch.cuda.mem_get_info(0)
        if "H800" not in gpu or total < 75 * 1024**3:
            raise RuntimeError("Expected an H800 80GB, received " + gpu)
        if free < 0.90 * total:
            raise RuntimeError("Allocated GPU has unexpected existing memory use; do not interfere with other processes")
        write(job_root / "runtime.json", {"hostname": socket.gethostname(), "gpu": gpu,
            "total_memory_bytes": total, "free_memory_before_server_bytes": free,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "vllm_version": importlib.metadata.version("vllm"), "torch_version": torch.__version__,
            "transformers_version": importlib.metadata.version("transformers")})
        model = root / "models/llama-3.1-8b-instruct"
        children.wait([children.spawn("tokenizer_preflight", [*common, "--mode", "tokenize"], runner.parent)])
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", PORT))
        command = [sys.executable, "-B", "-m", "vllm.entrypoints.openai.api_server",
            "--model", str(model), "--served-model-name", MODEL_ALIAS,
            "--host", "127.0.0.1", "--port", str(PORT), "--dtype", "bfloat16",
            "--tensor-parallel-size", "1", "--max-model-len", str(args.max_model_len),
            "--max-num-seqs", "8", "--gpu-memory-utilization", "0.85",
            "--enable-chunked-prefill", "--max-num-batched-tokens", "8192",
            "--generation-config", "vllm", "--override-generation-config",
            '{"top_k":-1,"top_p":1.0,"repetition_penalty":1.0}',
            "--enforce-eager", "--no-async-scheduling"]
        write(job_root / "server_command.json", {"argv": command, "base_url": BASE_URL})
        children.server = children.spawn("vllm_server", command, root)
        status(status="server_starting")
        timeout = time.monotonic() + 1800
        while True:
            children.check()
            if time.monotonic() > timeout:
                raise RuntimeError("Model server startup exceeded 30 minutes")
            try:
                with urlopen(BASE_URL + "/models", timeout=5) as response:
                    models = json.load(response)
                if [m.get("id") for m in models.get("data", [])] != [MODEL_ALIAS]:
                    raise RuntimeError("Served model ID does not match the frozen experiment")
                write(job_root / "healthy_models.json", models)
                break
            except (OSError, ValueError):
                time.sleep(2)
        status(status="fixed_case20_smoke")
        children.wait([children.spawn("smoke_case20", [*common, "--mode", "smoke"], runner.parent)])
        status(status="running", counts=counts(output))
        workers = [children.spawn(f"shard_{i}", [*common, "--mode", "run", "--shard-count", "2",
                    "--shard-index", str(i)], runner.parent) for i in range(2)]
        children.wait(workers, progress=lambda: status(status="running", counts=counts(output)))
        children.wait([children.spawn("final_summary", [*common, "--mode", "summarize"], runner.parent)])
        summary = read(output / "summary.json")
        if (summary.get("verification_passed") is not True or summary.get("expected_results") != 240
                or summary.get("terminal_results") != 240):
            raise RuntimeError("Final result identity/completeness verification failed")
        final = counts(output)
        if any(c["complete"] + c["strict_experiment_failure"] != 80 or c["other"] for c in final.values()):
            raise RuntimeError("Run ended without all 240 terminal results: " + str(final))
        status(status="complete", counts=final, terminal_results=240)
        return 0
    except BaseException as exc:
        status(status="failed_or_paused", error_type=type(exc).__name__, error=str(exc), counts=counts(output))
        return 1
    finally:
        children.cleanup()
        atexit.unregister(children.cleanup)
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
