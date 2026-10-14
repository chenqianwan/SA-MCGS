#!/usr/bin/env python3
"""Stage the frozen portable bundle and coordinator within our personal root.

No submission is performed by this script. Existing files must be identical.
"""
from pathlib import Path
import hashlib
import io
import json
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
REMOTE = "/aifs4su/hansirui_3rd/chenlong/q72awq_20260924"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    files = [p for p in (HERE / "package/repo").rglob("*") if p.is_file()]
    if not files or not (HERE / "package/repo/bundle_manifest.json").is_file():
        raise RuntimeError("Frozen experiment bundle is missing")
    if any(p.is_symlink() or p.name == ".env" or "__pycache__" in p.parts for p in files):
        raise RuntimeError("Unexpected symlink, environment file or bytecode in bundle")
    named = [(p, "repo/" + str(p.relative_to(HERE / "package/repo"))) for p in files]
    named += [(HERE / name, name) for name in ("run_awq_lea.py", "run_awq_lea.sbatch")]
    manifest = {name: {"sha256": digest(p), "bytes": p.stat().st_size} for p, name in named}
    receipt = {"remote_root": REMOTE, "files": manifest}
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for path, name in named:
            archive.add(path, arcname=name, recursive=False)
        data = (json.dumps(receipt, indent=2) + "\n").encode()
        info = tarfile.TarInfo("gpu_staging_manifest.json")
        info.size, info.mode = len(data), 0o600
        archive.addfile(info, io.BytesIO(data))
    code = r'''
import hashlib, io, json, os, pathlib, sys, tarfile
root = pathlib.Path("/aifs4su/hansirui_3rd/chenlong/q72awq_20260924")
if os.getuid() != 1083 or root.resolve() != root or root.stat().st_uid != os.getuid():
    raise SystemExit("Unexpected deployment root or account")
os.umask(0o077)
archive = tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()), mode="r:gz")
for member in archive.getmembers():
    relative = pathlib.PurePosixPath(member.name)
    if not member.isfile() or relative.is_absolute() or ".." in relative.parts:
        raise SystemExit("Unsafe archive member")
    path = root.joinpath(*relative.parts)
    if path.resolve() != path:
        raise SystemExit("Unexpected symlink in output path")
    content = archive.extractfile(member).read()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise SystemExit("Different file already staged: " + member.name)
    else:
        with path.open("xb") as stream:
            stream.write(content)
manifest = json.loads((root / "gpu_staging_manifest.json").read_text())
for relative, expected in manifest["files"].items():
    path = root / relative
    if path.stat().st_size != expected["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]:
        raise SystemExit("Staged hash mismatch: " + relative)
print(json.dumps({"verified": True, "files": len(manifest["files"]), "bytes": sum(v["bytes"] for v in manifest["files"].values()), "remote_root": str(root)}))
'''
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", "Group3_slogin", "/usr/bin/python3 -B -c " + shlex.quote(code)]
    result = subprocess.run(command, input=payload.getvalue(), capture_output=True, timeout=300)
    output = result.stdout.decode() + result.stderr.decode()
    print(output, end="")
    (HERE / "gpu_staging_receipt.txt").write_text(output)
    if result.returncode:
        raise SystemExit(result.returncode)
    (HERE / "gpu_staging_manifest.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
