"""Evidence checks and reports for gates G0 to G14.

Source: Protocole/PAQUET D'EXECUTION EBTA.md section 2 and section 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RequirementKind = Literal["identifier", "verdict_pass", "boolean_true"]


@dataclass(frozen=True)
class GateRequirement:
    name: str
    kind: RequirementKind


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    status: str
    missing: list[str]
    present: list[str]


def _requirements(kind: RequirementKind, *names: str) -> tuple[GateRequirement, ...]:
    return tuple(GateRequirement(name, kind) for name in names)


GATE_REQUIREMENTS: dict[str, tuple[GateRequirement, ...]] = {
    "G0": _requirements(
        "identifier", "config_id", "project_id", "research_family_id", "hypothesis_id", "process_version_id", "template_hash"
    ),
    "G1": _requirements("verdict_pass", "data_snapshots", "availability_timestamps", "anti_leakage_report"),
    "G2": _requirements(
        "verdict_pass", "registry_initialized", "candidate_catalog", "local_matrix", "independent_registry_review"
    ),
    "G3": _requirements("verdict_pass", "selection_rule", "train_only_calibration_log")
    + _requirements("identifier", "selected_candidate_id"),
    "G4": _requirements("verdict_pass", "wrc_report", "wrc_status", "wrc_family_matrix"),
    "G5": _requirements("verdict_pass", "robustness_report", "robustness_matrix", "pre_oos_robustness_verdict"),
    "G6": _requirements("verdict_pass", "execution_report", "cost_model", "capacity_grid", "nav_reconciliation"),
    "G7": _requirements(
        "verdict_pass", "pre_oos_manifest", "frozen_config", "test_reports", "independent_pre_oos_approval"
    ),
    "G8": _requirements("verdict_pass", "oos_access_log", "opening_authorization", "single_oos_execution_log"),
    "G9": _requirements("verdict_pass", "oos_report", "concatenated_oos_series", "oos_bootstrap_report", "power_report"),
    "G10": _requirements("verdict_pass", "economic_report", "statistical_gate_report", "economic_gate_report"),
    "G11": _requirements("verdict_pass", "validation_ready_manifest", "reproduction_report", "incubation_approval"),
    "G12": _requirements("verdict_pass", "incubation_report", "paper_trading_log", "monitoring_plan"),
    "G13": (
        *_requirements("verdict_pass", "deployment_certified_manifest"),
        *_requirements("identifier", "live_version_id"),
        *_requirements("verdict_pass", "kill_switch"),
        *_requirements("boolean_true", "live_approval"),
    ),
    "G14": _requirements("verdict_pass", "lifecycle_archive", "incident_log", "retention_policy"),
}


def validate_gates(evidence: dict) -> list[GateResult]:
    results: list[GateResult] = []
    for gate_id, requirements in GATE_REQUIREMENTS.items():
        missing = [
            requirement.name
            for requirement in requirements
            if not _requirement_satisfied(requirement, evidence.get(requirement.name))
        ]
        present = [
            requirement.name
            for requirement in requirements
            if _requirement_satisfied(requirement, evidence.get(requirement.name))
        ]
        status = "PASS" if not missing else "INCONCLUSIVE"
        results.append(GateResult(gate_id, status, missing, present))
    return results


def _requirement_satisfied(requirement: GateRequirement, value: object) -> bool:
    if requirement.kind == "identifier":
        return isinstance(value, str) and bool(value.strip())
    if requirement.kind == "verdict_pass":
        return isinstance(value, str) and value == "PASS"
    if requirement.kind == "boolean_true":
        return value is True
    raise ValueError(f"Unknown gate requirement kind: {requirement.kind!r}")


def gate_report(evidence: dict) -> dict:
    results = validate_gates(evidence)
    return {
        "summary": {
            "total": len(results),
            "pass": sum(1 for result in results if result.status == "PASS"),
            "inconclusive": sum(1 for result in results if result.status == "INCONCLUSIVE"),
        },
        "gates": [
            {
                "gate_id": result.gate_id,
                "status": result.status,
                "present": result.present,
                "missing": result.missing,
            }
            for result in results
        ],
    }
