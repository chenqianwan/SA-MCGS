"""Read-only admission of the separately audited localhost Qwen completion.

This admits one explicitly registered snapshot; it never changes the original
API route, protocol, budget, raw results, or scientific scoring policy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = "qwen2.5-72b"
REPOSITORY = "Qwen/Qwen2.5-72B-Instruct-AWQ"
REVISION = "698703eae6604af048a3d2f509995dc302088217"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_cluster_import(registry_path: Path, main_protocol: dict, frozen_manifest: dict) -> dict:
    registry = read(registry_path)
    require(registry.get("version") == 1 and registry.get("model") == MODEL,
            "Unexpected cluster import registry version/model")
    snapshot = Path(registry["snapshot_root"]).resolve()
    manifest_path = snapshot / "download_manifest.json"
    require(digest(manifest_path) == registry["download_manifest_sha256"],
            "Downloaded snapshot manifest changed after admission")
    manifest = read(manifest_path)
    require(manifest["remote_root"] == "/aifs4su/hansirui_3rd/chenlong/q72awq_20260924",
            "Unexpected cluster source root")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts,
                "Unsafe path in snapshot manifest")
        path = snapshot / relative
        require(path.resolve() == path and path.is_file(), "Missing or redirected snapshot file: " + name)
        require(path.stat().st_size == expected["bytes"] and digest(path) == expected["sha256"],
                "Downloaded file checksum mismatch: " + name)
    verification_path = snapshot / "cluster_import_verification.json"
    require(digest(verification_path) == registry["verification_sha256"],
            "Independent cluster import verification changed")
    independent_verification = read(verification_path)
    require(independent_verification.get("passed") is True and not independent_verification.get("failed_checks"),
            "Independent cluster import verification did not pass")

    output = snapshot / "results/lea_qwen80"
    pricing_path = output / "frozen_pricing.json"
    require(digest(pricing_path) == registry["pricing_sha256"], "Cluster pricing changed")
    pricing = read(pricing_path)
    require(set(pricing["models"]) == {MODEL}, "Unexpected model in cluster pricing")
    route = pricing["models"][MODEL]
    require(route["base_url"] == "http://127.0.0.1:18072/v1"
            and route["model_id"] == "qwen2.5-72b-instruct"
            and route["input_usd_per_million"] == 0 and route["output_usd_per_million"] == 0
            and route["checkpoint_repository"] == REPOSITORY and route["checkpoint_revision"] == REVISION,
            "Cluster route differs from the reviewed local deployment")
    protocol = read(output / "frozen_runner_protocol.json")
    require(protocol == main_protocol, "Cluster scientific protocol differs from the original completion")
    protocol_hash = hashlib.sha256(json.dumps(protocol, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    for relative, expected in protocol["code_sha256"].items():
        path = snapshot / "repo" / relative
        require(digest(path) == expected, "Cluster scientific source hash mismatch: " + relative)

    provenance_path = output / "deployment_provenance.json"
    require(digest(provenance_path) == registry["provenance_sha256"], "Cluster deployment provenance changed")
    provenance = read(provenance_path)
    bundle_path = snapshot / "repo/bundle_manifest.json"
    require(digest(bundle_path) == digest(HERE / "cluster_qwen72b/package/repo/bundle_manifest.json")
            and provenance["bundle_manifest_sha256"] == digest(bundle_path),
            "Portable graph/code bundle differs from the reviewed export")
    require(provenance["launcher_sha256"] == digest(snapshot / "repo/cluster_launcher.py")
            and provenance["checkpoint_repository"] == REPOSITORY
            and provenance["checkpoint_revision"] == REVISION,
            "Cluster adapter/checkpoint provenance mismatch")

    jobs = {job["runner_case_id"]: job for job in frozen_manifest["jobs"] if job["model"] == MODEL}
    plan = read(output / "case_plan.json")
    require(len(jobs) == len(plan) == 80 and {case["case_id"] for case in plan} == set(jobs),
            "Cluster plan is not the original complete Qwen80 target")
    for case in plan:
        frozen = jobs[case["case_id"]]
        for actual_key, expected_key in (("model", "model"), ("case_uid", "stable_case_uid"),
                ("planned_scc_clause_ids", "planned_scc_clause_ids"),
                ("planned_injection_identity", "planned_injection_identity"),
                ("source_result_sha256", "source_result_sha256")):
            require(case.get(actual_key) == frozen.get(expected_key),
                    "Cluster frozen case mismatch: " + case["case_id"] + "/" + actual_key)
    expected_paths = {f"{case}__lea.json" for case in jobs}
    require({path.name for path in (output / "results").glob("*__lea.json")} == expected_paths,
            "Cluster snapshot contains missing or unexpected result files")
    # Individual result identity, model, route, protocol and metrics are checked
    # again by the existing scientific summarizer for every admitted row.
    return {"model": MODEL, "run_dir": output, "pricing": pricing,
            "pricing_hash": digest(pricing_path), "protocol_hash": protocol_hash,
            "verification": {"registry": str(registry_path), "snapshot_root": str(snapshot),
                "snapshot_manifest_sha256": digest(manifest_path),
                "independent_verification_sha256": digest(verification_path),
                "scientific_protocol_identical": True, "cases": 80,
                "deployment": provenance, "downloaded_files_verified": len(manifest["files"])}}
