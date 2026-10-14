#!/Users/chenlong/.pyenv/versions/3.11.0/bin/python
"""Read-only SSH retrieval and identity audit of completed Qwen80 artifacts.

Remote files are never written. No checkpoint weights or raw response cache
are downloaded. Every retrieved byte has a remote SHA-256 receipt.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
MAIN = HERE.parent
ROOT = MAIN.parents[3]
DEST = HERE / "retrieved_final_20260924"
REMOTE = "/aifs4su/hansirui_3rd/chenlong/q72awq_20260924"

REMOTE_CODE = r'''
from pathlib import Path
import datetime,hashlib,io,json,os,subprocess,sys,tarfile
root=Path('/aifs4su/hansirui_3rd/chenlong/q72awq_20260924')
if root.resolve()!=root:raise RuntimeError('Remote root unexpectedly redirected')
selected=set()
for p in root.glob('*.json'):selected.add(p)
for name in ['run_awq_lea.py','run_awq_lea.sbatch','run_awq_lea_resume.py','run_awq_lea_resume.sbatch']:
    selected.add(root/name)
out=root/'results/lea_qwen80'
for p in out.iterdir():
    if p.is_file() and p.suffix in {'.json','.jsonl','.csv','.md'}:selected.add(p)
for sub in ['results','case_status','worker_status']:
    selected.update((out/sub).glob('*.json'))
selected.update((out/'call_logs').glob('*.jsonl'))
for job in ['394281','394534']:
    selected.update((root/'runs'/job).glob('*.json'))
for name in ['config.json','generation_config.json','tokenizer_config.json','model.safetensors.index.json']:
    selected.add(root/'model'/name)
for name in ['bundle_manifest.json','PACKAGE_FILES_SHA256.json','requirements_runtime.txt','README_PORTABLE_ZH.md']:
    selected.add(root/'repo'/name)
selected.update((root/'repo').rglob('*.py'))
for name in ['qwen80_case_plan.json','historical_provider_confirmation.json']:
    selected.add(root/'repo/portable_data'/name)
files={};entries={}
def capture(path):
    if path.is_symlink() or path.resolve()!=path or root not in path.parents or not path.is_file():
        raise RuntimeError('Unsafe/unavailable retrieval path: '+str(path))
    before=path.stat();data=path.read_bytes();after=path.stat()
    if (before.st_mtime_ns,before.st_size)!=(after.st_mtime_ns,after.st_size):
        raise RuntimeError('File changed during retrieval: '+str(path))
    return data,{'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'mtime_ns':after.st_mtime_ns,'source':'remote_file'}
for path in sorted(selected):
    relative=str(path.relative_to(root));data,meta=capture(path)
    files[relative]=data;entries[relative]=meta
seal=json.loads((root/'repo/PACKAGE_FILES_SHA256.json').read_text())
bundle_checks={}
for relative,expected in sorted(seal.items()):
    data,actual=capture(root/'repo'/relative)
    bundle_checks[relative]={**actual,'expected_sha256':expected,'matches':actual['sha256']==expected}
    if actual['sha256']!=expected:raise RuntimeError('Remote deployed bundle mismatch: '+relative)
model_checks={}
for name in ['config.json','generation_config.json','tokenizer_config.json','model.safetensors.index.json','tokenizer.json','merges.txt','vocab.json']:
    data,actual=capture(root/'model'/name);model_checks[name]=actual
slurm={}
env=dict(os.environ,SLURM_CONF='/cm/shared/apps/slurm/var/etc/slurm/slurm.conf')
for job in ['394281','394534']:
    r=subprocess.run(['/cm/shared/apps/slurm/current/bin/sacct','-n','-P','-j',job,'--format=JobID,State,ExitCode,NodeList,Start,End,Elapsed,AllocTRES'],env=env,text=True,capture_output=True)
    slurm[job]={'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
captured=datetime.datetime.now(datetime.timezone.utc).isoformat()
evidence={'captured_at_utc':captured,'remote_root':str(root),'remote_read_only':True,
          'weights_downloaded':False,'raw_call_cache_downloaded':False,
          'bundle_file_checks':bundle_checks,'model_metadata_checks':model_checks,'slurm_accounting':slurm}
name='retrieval_evidence/remote_integrity_snapshot.json'
data=(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n').encode()
files[name]=data;entries[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'mtime_ns':None,'source':'generated_read_only_remote_snapshot'}
manifest={'remote_root':str(root),'retrieved_at_utc':captured,'files':entries,
          'file_count':len(entries),'total_bytes':sum(v['bytes'] for v in entries.values()),
          'exclusions':['model weight shards','raw call_cache responses','GPU/runtime caches','source data already verified by remote bundle hashes']}
files['download_manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
    for relative,data in sorted(files.items()):
        member=tarfile.TarInfo(relative);member.size=len(data);member.mode=0o600
        archive.addfile(member,io.BytesIO(data))
'''


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def retrieve():
    DEST.mkdir(parents=True, exist_ok=True)
    archive = DEST / "retrieved_artifacts.tar.gz"
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15",
               "Group3_slogin", "/usr/bin/python3 -B -c " + shlex.quote(REMOTE_CODE)]
    with archive.open("wb") as handle:
        result = subprocess.run(command, stdout=handle, stderr=subprocess.PIPE, timeout=300)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        names = [m.name for m in members]
        if len(set(names)) != len(names):
            raise RuntimeError("Duplicate archive members")
        manifest = json.loads(stream.extractfile("download_manifest.json").read())
        if set(names) != set(manifest["files"]) | {"download_manifest.json"}:
            raise RuntimeError("Archive/download-manifest closure mismatch")
        for member in members:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or not member.isfile():
                raise RuntimeError("Unsafe archive member")
            data = stream.extractfile(member).read()
            if member.name != "download_manifest.json":
                expected = manifest["files"][member.name]
                if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
                    raise RuntimeError("Retrieved artifact SHA/size mismatch: " + member.name)
            target = DEST.joinpath(*relative.parts)
            if target.resolve() != target:
                raise RuntimeError("Local destination redirected")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    write(DEST / "retrieval_receipt.json", {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "ssh_host": "Group3_slogin",
        "remote_root": REMOTE, "remote_read_only": True, "api_calls": 0,
        "archive_sha256": sha(archive), "archive_bytes": archive.stat().st_size,
        "download_manifest_sha256": sha(DEST / "download_manifest.json"),
        "downloaded_file_count": len(manifest["files"]), "sha256_verified_files": len(manifest["files"]),
    })


def verify():
    manifest = read(DEST / "download_manifest.json")
    checks = []
    def check(name, expected, actual):
        checks.append({"name": name, "expected": expected, "actual": actual, "passed": actual == expected})
    for name, expected in manifest["files"].items():
        check("download_sha256:" + name, expected["sha256"], sha(DEST / name))
        check("download_bytes:" + name, expected["bytes"], (DEST / name).stat().st_size)
    evidence = read(DEST / "retrieval_evidence/remote_integrity_snapshot.json")
    local_repo = HERE / "package/repo"
    local_seal = read(local_repo / "PACKAGE_FILES_SHA256.json")
    remote_seal = read(DEST / "repo/PACKAGE_FILES_SHA256.json")
    check("remote_and_local_package_seal", local_seal, remote_seal)
    check("remote_bundle_check_closure", sorted(local_seal), sorted(evidence["bundle_file_checks"]))
    for name, expected in local_seal.items():
        check("local_package_hash:" + name, expected, sha(local_repo / name))
        check("remote_deployed_package_hash:" + name, expected, evidence["bundle_file_checks"][name]["sha256"])
    out = DEST / "results/lea_qwen80"
    pricing = read(out / "frozen_pricing.json")
    protocol = read(out / "frozen_runner_protocol.json")
    provenance = read(out / "deployment_provenance.json")
    bundle = read(DEST / "repo/bundle_manifest.json")
    route = pricing["models"]["qwen2.5-72b"]
    check("main_and_cluster_scientific_protocol_identical", read(MAIN / "frozen_runner_protocol.json"), protocol)
    check("local_route_base_url", "http://127.0.0.1:18072/v1", route["base_url"])
    check("local_route_model", "qwen2.5-72b-instruct", route["model_id"])
    check("local_input_price", 0, route["input_usd_per_million"])
    check("local_output_price", 0, route["output_usd_per_million"])
    check("external_api_spending_allowed_usd", 0, pricing["external_api_spending_allowed_usd"])
    check("provenance_bundle_hash", sha(DEST / "repo/bundle_manifest.json"), provenance["bundle_manifest_sha256"])
    check("provenance_launcher_hash", sha(DEST / "repo/cluster_launcher.py"), provenance["launcher_sha256"])
    for code, expected in protocol["code_sha256"].items():
        check("protocol_original_code:" + code, expected, sha(DEST / "repo" / code))
        check("scientific_original_code:" + code, bundle["unchanged_code_sha256"][code], expected)
    for name in ("portable_preflight.json", "tokenization_report.json"):
        raw = read(out / name)
        check(name + ":passed", True, raw["passed"])
        check(name + ":cases", 80, raw["cases"])
        check(name + ":bundle_hash", provenance["bundle_manifest_sha256"], raw["bundle_manifest_sha256"])
    tokenization = read(out / "tokenization_report.json")
    for name, expected in tokenization["tokenizer_files_sha256"].items():
        check("tokenizer_current_hash:" + name, expected, evidence["model_metadata_checks"][name]["sha256"])
    original = read(MAIN / "frozen_manifest.json")
    frozen = {c["runner_case_id"]: c for c in original["jobs"] if c["model"] == "qwen2.5-72b"}
    plan = {c["case_id"]: c for c in read(out / "case_plan.json")}
    paths = {p.name.removesuffix("__lea.json"): p for p in (out / "results").glob("*__lea.json")}
    original_captures = {row["case_id"]: row for row in json.loads(gzip.decompress((local_repo / "portable_data/original_prompt_capture.json.gz").read_bytes()))}
    check("frozen_qwen_count", 80, len(frozen))
    check("runtime_plan_case_set", sorted(frozen), sorted(plan))
    check("result_case_set", sorted(frozen), sorted(paths))
    spec = importlib.util.spec_from_file_location("qwen_import_audit", ROOT / "2026NAACL/SA-MCGS/annotation_prep/baseline_audit/audit_baseline_coverage.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    pricing_sha = sha(out / "frozen_pricing.json")
    protocol_sha = canonical_hash(protocol)
    case_rows = []
    for case_id, cell in sorted(frozen.items()):
        if case_id not in paths or case_id not in plan:
            continue
        runtime = plan[case_id]
        result = read(paths[case_id])
        planned = {**cell, "planned_scc_clause_ids": cell["planned_scc_clause_ids"], "planned_injection_identity": cell["planned_injection_identity"]}
        exact, detail = audit.validate_identity(result, planned)
        fields = {
            "identity_exact": (True, exact), "model": ("qwen2.5-72b", result.get("model")),
            "method": ("lea", result.get("method")), "window_size": (4, result.get("window_size")),
            "completion_status": ("complete", result.get("completion_status")),
            "cost_audit_error_empty": (False, bool(result.get("cost_audit_error"))),
            "case_id": (case_id, result.get("case_id")), "case_uid": (cell["stable_case_uid"], result.get("case_uid")),
            "planned_scc_fingerprint": (cell["planned_scc_fingerprint"], result.get("planned_scc_fingerprint")),
            "actual_scc_fingerprint": (cell["planned_scc_fingerprint"], result.get("actual_scc_fingerprint")),
            "actual_injection_identity": (cell["planned_injection_identity"], result.get("actual_injection_identity")),
            "dataset_revision": (bundle["graphs"][cell["domain"]]["dataset_revision"], (result.get("actual_case_identity") or {}).get("dataset_revision")),
            "deterministic_windows": (original_captures[case_id]["deterministic_windows"], result.get("deterministic_windows")),
            "source_result_sha256": (cell["source_result_sha256"], result.get("source_result_sha256")),
            "source_sa_record_sha256": (cell["source_sa_record_sha256"], result.get("source_sa_record_sha256")),
            "runtime_case_uid": (cell["stable_case_uid"], runtime.get("case_uid")),
            "runtime_physical_scc_uid": (cell["physical_scc_uid"], runtime.get("physical_scc_uid")),
            "result_route": (route, result.get("provider_route")),
            "result_pricing_sha256": (pricing_sha, result.get("pricing_sha256")),
            "result_protocol_sha256": (protocol_sha, result.get("protocol_sha256")),
        }
        for field, (expected, actual) in fields.items():
            check(case_id + ":" + field, expected, actual)
        source_relative = runtime["source_result_repo_relpath"]
        check(case_id + ":source_bundle_hash", cell["source_result_sha256"].removeprefix("sha256:"), evidence["bundle_file_checks"][source_relative]["sha256"])
        check(case_id + ":original_main_source_hash", cell["source_result_sha256"].removeprefix("sha256:"), sha(Path(cell["source_result_file"])))
        case_rows.append({"case_id": case_id, "model": cell["model"], "main_case_order": cell["main_case_order"],
                          "stable_case_uid": cell["stable_case_uid"], "physical_scc_uid": cell["physical_scc_uid"],
                          "domain": cell["domain"], "scc_size": cell["scc_size"], "template": cell["template"],
                          "source_file": str(paths[case_id]), "source_sha256": sha(paths[case_id]),
                          "identity_exact": exact, "identity_detail": detail,
                          "all_case_checks_passed": all(expected == actual for expected, actual in fields.values())})
    server_commands = {job: read(DEST / f"runs/{job}/server_command.json") for job in ("394281", "394534")}
    check("restart_server_command_identical", server_commands["394281"], server_commands["394534"])
    original_checkpoint = read(DEST / "runs/394281/checkpoint_verified.json")
    for job in ("394281", "394534"):
        checkpoint = read(DEST / f"runs/{job}/checkpoint_verified.json")
        check("checkpoint_content_same_except_verification_time:" + job,
              {key: value for key, value in original_checkpoint.items() if key != "verified_at"},
              {key: value for key, value in checkpoint.items() if key != "verified_at"})
        check("checkpoint_download_marker_hash:" + job, sha(DEST / "model_download_complete.json"), checkpoint["download_marker_sha256"])
        check("checkpoint_revision:" + job, route["checkpoint_revision"], checkpoint["revision"])
    runtime_keys = ("gpu_name", "gpu_memory_bytes", "vllm_version", "torch_version", "transformers_version")
    runtimes = {job: read(DEST / f"runs/{job}/runtime.json") for job in ("394281", "394534")}
    check("restart_gpu_and_runtime_versions_identical", {key: runtimes["394281"][key] for key in runtime_keys},
          {key: runtimes["394534"][key] for key in runtime_keys})
    marker = read(DEST / "model_download_complete.json")
    check("download_marker_complete", "complete", marker["state"])
    check("download_marker_verified", True, marker["verified"])
    check("download_marker_checkpoint_revision", route["checkpoint_revision"], marker["revision"])
    marker_files = {Path(row["path"]).name: row for row in marker["files"]}
    official = read(DEST / "official_model_metadata.json")
    for row in official["siblings"]:
        if row["rfilename"].endswith(".safetensors"):
            check("official_weight_marker_sha:" + row["rfilename"], row["lfs"]["sha256"], marker_files[row["rfilename"]]["sha256"])
    for name, current in evidence["model_metadata_checks"].items():
        check("current_model_metadata_vs_verified_download:" + name, marker_files[name]["sha256"], current["sha256"])
    final_status = read(DEST / "runs/394534/status.json")
    check("final_job_complete_status", "complete", final_status["status"])
    check("final_job_complete_count", 80, final_status["complete"])
    check("final_job_strict_failures", 0, final_status["strict_failures"])
    reservations, settlements = {}, {}
    ledger_anomalies = []
    for number, line in enumerate((out / "budget_ledger.jsonl").read_text().splitlines(), 1):
        entry = json.loads(line)
        rid = entry["reservation_id"]
        if entry.get("pricing_sha256") != pricing_sha:
            ledger_anomalies.append({"line": number, "reason": "pricing_sha_mismatch"})
        if entry["event"] == "reserve":
            if (rid in reservations or entry.get("reserved_nd") != 0 or entry.get("reserved_usd") != 0
                or entry.get("case_id") not in frozen or entry.get("protocol_sha256") != protocol_sha
                or entry.get("base_url") != route["base_url"] or entry.get("model") != "qwen2.5-72b"):
                ledger_anomalies.append({"line": number, "reason": "invalid_or_duplicate_reservation"})
            reservations[rid] = entry
        elif entry["event"] == "settle":
            if rid not in reservations or rid in settlements or entry.get("charged_nd") != 0 or entry.get("charged_usd") != 0:
                ledger_anomalies.append({"line": number, "reason": "invalid_or_duplicate_settlement"})
            settlements[rid] = entry
        else:
            ledger_anomalies.append({"line": number, "reason": "unknown_event"})
    check("full_ledger_route_pricing_zero_cost_and_sequence", [], ledger_anomalies)
    budget = read(out / "budget_status.json")
    check("budget_reservation_count", len(reservations), budget["api_reservations"])
    check("budget_settlement_count", len(settlements), budget["settled_calls"])
    check("external_charged_or_assumed_usd", 0, budget["charged_or_conservatively_assumed_usd"])
    check("external_unresolved_reserved_usd", 0, budget["unresolved_reservations_usd"])
    check("external_committed_usd", 0, budget["committed_upper_bound_usd"])
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "remote_root": REMOTE,
              "download_manifest_sha256": sha(DEST / "download_manifest.json"),
              "main_frozen_manifest_sha256": sha(MAIN / "frozen_manifest.json"),
              "local_bundle_manifest_sha256": sha(local_repo / "bundle_manifest.json"),
              "cluster_pricing_file_sha256": pricing_sha, "cluster_protocol_canonical_sha256": protocol_sha,
              "cluster_protocol_file_sha256": sha(out / "frozen_runner_protocol.json"),
              "ledger_summary": {"reservations": len(reservations), "settlements": len(settlements),
                  "unsettled_reservations": len(set(reservations) - set(settlements)),
                  "unsettled_amount_usd": 0, "external_api_charged_usd": 0,
                  "note": "Four zero-dollar in-flight reservations from the first job remain in the append-only audit ledger; no monetary exposure or missing final scientific result."},
              "checkpoint_verification_scope": "Checkpoint weight bytes were not downloaded/rehashed during retrieval; initial full-download SHA receipts match official LFS and both startup header/index verification records; current small model files were rehashed remotely.",
              "results_directory": str(out / "results"), "cluster_output_directory": str(out),
              "verified_case_count": len(case_rows), "checks": checks, "cases": case_rows,
              "checks_passed": sum(x["passed"] for x in checks), "checks_total": len(checks),
              "failed_checks": [x for x in checks if not x["passed"]],
              "passed": all(x["passed"] for x in checks), "api_calls": 0,
              "import_policy": "Use an explicit external-Qwen source manifest and the unchanged cluster pricing/protocol/deployment provenance. Do not rewrite original result bytes or main API-run frozen files. Cluster token usage is scientific compute cost, external API spend is zero; retain original paid-run budget separately."}
    write(DEST / "cluster_import_verification.json", report)
    print(json.dumps({key: report[key] for key in ("passed", "verified_case_count", "checks_passed", "checks_total", "failed_checks", "results_directory")}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        retrieve()
    raise SystemExit(verify())
