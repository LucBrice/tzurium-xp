"""End-to-end EBTA package validation.

Source: Protocole/PAQUET D'EXECUTION EBTA.md sections 2, 3, 5, and 6.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ebta_engine.manifests.manifest_builder import verify_manifest
from ebta_engine.validators.artifact_validators import validate_json_file, validate_jsonl_file
from ebta_engine.validators.gate_validator import gate_report
from ebta_engine.validators.invariant_validator import validate_invariants


REQUIRED_PACKAGE_PATHS = {
    "config.json",
    "registry.jsonl",
    "oos_access_log.jsonl",
    "reports/gates.json",
    "reports/wrc.json",
    "reports/robustness.json",
    "reports/oos.json",
    "reports/economic.json",
    "reports/incubation_gate.json",
    "reports/execution.json",
    "reports/reproduction.json",
    "reports/invariant_evidence.json",
    "reports/search_space.json",
    "reports/optimization_log.json",
    "reports/ml_manifest.json",
    "reports/complexity_selection.json",
    "reports/candidate_matrix.json",
    "reports/data_availability.json",
    "reports/fold_schedule.json",
    "reports/registry_review.json",
    "reports/detrending.json",
    "series/oos_primary_returns.json",
    "manifests/reproducibility_manifest.json",
}

OPTIONAL_G_BIAS_PATH = "reports/g_bias.json"


def validate_package_dir(package_dir: Path, *, enforce_bias_governance: bool | None = None) -> dict:
    missing_paths = sorted(path for path in REQUIRED_PACKAGE_PATHS if not (package_dir / path).exists())
    schema_errors = []
    if (package_dir / "config.json").exists():
        schema_errors.extend(_format_errors("config.json", validate_json_file(package_dir / "config.json", "config.schema.json")))
    if (package_dir / "registry.jsonl").exists():
        schema_errors.extend(
            _format_errors(
                "registry.jsonl",
                validate_jsonl_file(package_dir / "registry.jsonl", "experiment_registry_event.schema.json"),
            )
        )
    if (package_dir / "oos_access_log.jsonl").exists():
        schema_errors.extend(
            _format_errors(
                "oos_access_log.jsonl",
                validate_jsonl_file(package_dir / "oos_access_log.jsonl", "oos_access_event.schema.json"),
            )
        )
    manifest_path = package_dir / "manifests" / "reproducibility_manifest.json"
    if manifest_path.exists():
        schema_errors.extend(
            _format_errors(
                "manifests/reproducibility_manifest.json",
                validate_json_file(manifest_path, "reproducibility_manifest.schema.json"),
            )
        )

    manifest_failures = []
    manifest_artifact_failures = []
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_failures = verify_manifest(package_dir, manifest)
        manifest_artifact_failures = _manifest_artifact_failures(manifest)

    evidence = _load_json(package_dir / "reports" / "gates.json", default={})
    invariant_evidence = _load_json(package_dir / "reports" / "invariant_evidence.json", default={})
    invariant_evidence["manifest_hash_failures"] = manifest_failures
    invariant_results = validate_invariants(invariant_evidence)
    gates = gate_report(evidence)
    gate_failures = _gate_failures(gates)
    invariant_failures = _invariant_failures(invariant_results)
    semantic_errors = _semantic_consistency_errors(package_dir)
    bias_gate_report = _load_json(package_dir / OPTIONAL_G_BIAS_PATH, default={})
    bias_gate_failures = _bias_gate_failures(
        bias_gate_report,
        enforce_bias_governance=_enforce_bias_governance(enforce_bias_governance),
        report_exists=(package_dir / OPTIONAL_G_BIAS_PATH).exists(),
    )

    return {
        "missing_paths": missing_paths,
        "schema_errors": schema_errors,
        "manifest_failures": manifest_failures,
        "manifest_artifact_failures": manifest_artifact_failures,
        "gate_report": gates,
        "gate_failures": gate_failures,
        "invariant_results": [result.__dict__ for result in invariant_results],
        "invariant_failures": invariant_failures,
        "semantic_errors": semantic_errors,
        "bias_gate_report": bias_gate_report,
        "bias_gate_failures": bias_gate_failures,
        "status": "PASS"
        if not (
            missing_paths
            or schema_errors
            or manifest_failures
            or manifest_artifact_failures
            or gate_failures
            or invariant_failures
            or semantic_errors
            or bias_gate_failures
        )
        else "FAIL",
    }


def _format_errors(path: str, errors: list) -> list[str]:
    return [f"{path} {error.path}: {error.message}" for error in errors]


def _load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_artifact_failures(manifest: dict) -> list[str]:
    manifest_paths = {artifact.get("path") for artifact in manifest.get("artifacts", [])}
    missing = sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json" and path not in manifest_paths)
    return [f"manifest missing required artifact: {path}" for path in missing]


def _gate_failures(report: dict) -> list[str]:
    return [
        f"{gate['gate_id']} {gate['status']}: missing {gate['missing']}"
        for gate in report.get("gates", [])
        if gate.get("status") != "PASS"
    ]


def _invariant_failures(results: list) -> list[str]:
    return [
        f"{result.invariant_id} {result.status}: {result.message}"
        for result in results
        if result.status != "PASS"
    ]


def _enforce_bias_governance(enforce_bias_governance: bool | None) -> bool:
    if enforce_bias_governance is not None:
        return enforce_bias_governance
    return os.environ.get("EBTA_ENABLE_BIAS_GOVERNANCE", "").strip().lower() in {"1", "true", "yes", "on"}


def _bias_gate_failures(report: dict, *, enforce_bias_governance: bool, report_exists: bool) -> list[str]:
    if not report_exists:
        return ["missing optional enforced artifact: reports/g_bias.json"] if enforce_bias_governance else []
    status = report.get("status")
    if status != "PASS":
        return [f"G-BIAS {status or 'MISSING_STATUS'}"]
    return []


def _semantic_consistency_errors(package_dir: Path) -> list[str]:
    errors: list[str] = []
    config = _load_json(package_dir / "config.json", default={})
    reports_dir = package_dir / "reports"
    search_space = _load_json(reports_dir / "search_space.json", default={})
    candidate_matrix = _load_json(reports_dir / "candidate_matrix.json", default={})
    wrc = _load_json(reports_dir / "wrc.json", default={})
    oos = _load_json(reports_dir / "oos.json", default={})
    economic = _load_json(reports_dir / "economic.json", default={})
    invariant_evidence = _load_json(reports_dir / "invariant_evidence.json", default={})
    incubation_gate = _load_json(reports_dir / "incubation_gate.json", default={})
    fold_schedule = _load_json(reports_dir / "fold_schedule.json", default={})

    configured_count = config.get("candidate_space", {}).get("candidate_count")
    if configured_count is not None and search_space.get("candidate_count") is not None:
        if configured_count != search_space["candidate_count"]:
            errors.append(
                f"candidate count mismatch: config={configured_count} search_space={search_space['candidate_count']}"
            )

    candidate_ids = candidate_matrix.get("candidate_ids", [])
    if configured_count is not None and candidate_ids and configured_count != len(candidate_ids):
        errors.append(f"candidate count mismatch: config={configured_count} candidate_matrix={len(candidate_ids)}")
    if candidate_ids and wrc.get("candidate_ids") and sorted(candidate_ids) != sorted(wrc["candidate_ids"]):
        errors.append("WRC candidate_ids do not match candidate_matrix candidate_ids")

    preregistration = search_space.get("pre_registration", {})
    if search_space and preregistration.get("missing_fields"):
        errors.append(f"search_space missing pre-registration fields: {preregistration['missing_fields']}")

    statistical_plan = config.get("statistical_plan", {})
    if "wrc_bootstrap_replications" in statistical_plan and wrc.get("replications") is not None:
        if wrc["replications"] != statistical_plan["wrc_bootstrap_replications"]:
            errors.append("WRC replications do not match preregistered statistical_plan")
    if oos.get("replications") is not None:
        expected_oos_replications = statistical_plan.get("oos_bootstrap_replications")
        if expected_oos_replications != 5000:
            errors.append("OOS bootstrap replications must be preregistered as 5000 under DN-022")
        elif oos["replications"] != expected_oos_replications:
            errors.append("OOS replications do not match preregistered statistical_plan")

    if fold_schedule and fold_schedule.get("status") != "PASS":
        errors.append(f"fold_schedule status is {fold_schedule.get('status')}")
    if incubation_gate and incubation_gate.get("status") != "PASS":
        errors.append(f"incubation_gate status is {incubation_gate.get('status')}")
    if economic and economic.get("global_status") is not None and economic.get("global_status") != "PASS":
        errors.append(f"economic global_status is {economic.get('global_status')}")
    if economic and economic.get("economic_status") == "PASS":
        for key in ["thresholds", "observed_values", "capacity_grid"]:
            if key not in economic:
                errors.append(f"economic report missing {key}")

    gate_reports = invariant_evidence.get("gate_reports", {})
    if (
        wrc.get("verdict") is not None
        and economic.get("statistical_status") is not None
        and wrc["verdict"] != economic["statistical_status"]
    ):
        errors.append(
            "statistical verdict mismatch: "
            f"wrc.verdict={wrc['verdict']!r} "
            f"economic.statistical_status={economic['statistical_status']!r}"
        )
    owner_values = {
        "statistical": economic.get("statistical_status", wrc.get("verdict")),
        "economic": economic.get("economic_status", economic.get("economic_verdict")),
        "final": economic.get("global_status"),
    }
    for field, owner_value in owner_values.items():
        persisted_value = gate_reports.get(field)
        if owner_value is not None and persisted_value != owner_value:
            errors.append(
                "persisted gate verdict mismatch: "
                f"invariant_evidence.gate_reports.{field}={persisted_value!r} "
                f"owner={owner_value!r}"
            )

    return errors
