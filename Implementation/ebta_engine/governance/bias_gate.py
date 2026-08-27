"""Transversal G-BIAS gate aggregation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .candidate_family_checker import check_candidate_family
from .metric_lock_checker import check_metric_lock
from .registry_completeness_checker import check_registry_completeness
from .robustness_gate_checker import check_robustness_gate


BLOCKING_SEVERITIES = {"LEVEL_2", "LEVEL_3", "LEVEL_4", "LEVEL_5"}
OPEN_STATUSES = {"OPEN", "FAIL", "INCONCLUSIVE", "BURNED"}


def evaluate_bias_gate(
    *,
    candidate_registry: list[dict[str, Any]] | None,
    statistical_family_matrix: dict[str, Any] | None,
    preregistration_manifest: dict[str, Any] | None,
    executed_configuration: dict[str, Any] | None,
    robustness_plan: dict[str, Any] | None,
    robustness_matrix: dict[str, Any] | None,
    oos_access_log: list[dict[str, Any]] | None,
    incident_log: list[dict[str, Any]] | None,
    reviewer_report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Aggregate G-BIAS checkers into PASS/FAIL/INCONCLUSIVE/BURNED."""
    checked_artifacts = [
        "candidate_registry",
        "statistical_family_matrix",
        "preregistration_manifest",
        "robustness_matrix",
        "oos_access_log",
        "incident_log",
        "reviewer_report",
    ]
    checker_reports: list[dict[str, Any]] = []
    checker_reports.append(check_registry_completeness(candidate_registry or [], statistical_family_matrix or {}))
    checker_reports.append(check_candidate_family(candidate_registry or [], statistical_family_matrix or {}))
    checker_reports.append(check_metric_lock(preregistration_manifest or {}, executed_configuration or {}))
    checker_reports.append(check_robustness_gate(robustness_plan or {}, robustness_matrix or {}))

    blocking_incidents = _blocking_incidents(incident_log or [])
    generated_incidents = [
        incident
        for report in checker_reports
        if report.get("status") == "FAIL"
        for incident in report.get("incidents", [])
        if incident.get("severity") in BLOCKING_SEVERITIES
    ]
    warnings: list[str] = []
    if not reviewer_report or not reviewer_report.get("independent_reviewer") or reviewer_report.get("status") != "PASS":
        warnings.append("missing independent G-BIAS reviewer PASS")

    if _burned_oos(oos_access_log or [], blocking_incidents):
        status = "BURNED"
    elif any(report["status"] == "FAIL" for report in checker_reports) or blocking_incidents or generated_incidents:
        status = "FAIL"
    elif any(report["status"] == "INCONCLUSIVE" for report in checker_reports) or warnings:
        status = "INCONCLUSIVE"
    else:
        status = "PASS"

    return {
        "artifact_type": "g_bias_report",
        "gate": "G-BIAS",
        "status": status,
        "blocking_incidents": blocking_incidents + generated_incidents,
        "warnings": warnings,
        "checked_artifacts": checked_artifacts,
        "checker_reports": checker_reports,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_normative": "SOP 13; DN-042 to DN-047",
    }


def _blocking_incidents(incident_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        incident for incident in incident_log
        if incident.get("status") in OPEN_STATUSES and incident.get("severity") in BLOCKING_SEVERITIES
    ]


def _burned_oos(oos_access_log: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> bool:
    if any(event.get("oos_state") == "BURNED" or event.get("unauthorized_access_detected") for event in oos_access_log):
        return True
    return any(
        incident.get("status") == "BURNED"
        or (
            incident.get("bias_id") in {"BIAS-014", "BIAS-015", "BIAS-017", "BIAS-020"}
            and incident.get("severity") in {"LEVEL_4", "LEVEL_5"}
        )
        for incident in incidents
    )
