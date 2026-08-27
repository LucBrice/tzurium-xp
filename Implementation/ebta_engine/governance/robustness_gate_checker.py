"""Robustness shopping checker for EBTA G-BIAS."""

from __future__ import annotations

from typing import Any


def check_robustness_gate(
    preregistered_plan: dict[str, Any],
    robustness_report: dict[str, Any],
) -> dict[str, Any]:
    """Detect missing, added, or post-hoc robustness stress-tests."""
    expected_ids = _stress_ids(preregistered_plan)
    executed_ids = set(robustness_report.get("executed_stress_ids") or robustness_report.get("stress_ids") or [])
    violations: list[dict[str, Any]] = []

    if not expected_ids or not executed_ids:
        return _report("INCONCLUSIVE", [{"rule": "ROBUSTNESS_EVIDENCE_MISSING", "bias_id": "BIAS-010"}])

    missing = sorted(expected_ids - executed_ids)
    if missing:
        violations.append({
            "rule": "PREREGISTERED_STRESS_TEST_REMOVED",
            "missing_stress_ids": missing,
            "bias_id": "BIAS-010",
            "description": "Preregistered robustness stress-tests were not executed or were removed.",
        })

    added = sorted(executed_ids - expected_ids)
    diagnostic_only = set(robustness_report.get("diagnostic_only_stress_ids") or [])
    non_diagnostic_added = sorted(set(added) - diagnostic_only)
    if non_diagnostic_added:
        violations.append({
            "rule": "POST_HOC_STRESS_TEST_USED_DECISIONALLY",
            "stress_ids": non_diagnostic_added,
            "bias_id": "BIAS-011",
            "description": "Stress-tests added after preregistration are not marked diagnostic_only.",
        })

    removed_unfavorable = robustness_report.get("removed_unfavorable_stress_ids") or []
    if removed_unfavorable:
        violations.append({
            "rule": "UNFAVORABLE_STRESS_TEST_REMOVED",
            "stress_ids": sorted(removed_unfavorable),
            "bias_id": "BIAS-012",
            "description": "Unfavorable stress-tests were removed from the robustness evidence.",
        })

    if robustness_report.get("selects_new_variant"):
        violations.append({
            "rule": "ROBUSTNESS_USED_FOR_RESELECTION",
            "bias_id": "BIAS-010",
            "description": "Robustness evidence is being used to select a new undeclared variant.",
        })

    return _report("PASS" if not violations else "FAIL", violations)


def _stress_ids(plan: dict[str, Any]) -> set[str]:
    if plan.get("stress_ids"):
        return set(plan["stress_ids"])
    return {scenario["stress_id"] for scenario in plan.get("scenarios", []) if scenario.get("stress_id")}


def _report(status: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    incidents = [
        {
            "bias_id": violation.get("bias_id", "BIAS-010"),
            "severity": "LEVEL_2",
            "status": "OPEN",
            "decision": "BLOCK_OOS_AND_RECONCILE_ROBUSTNESS_PLAN",
            "evidence_path": "reports/robustness.json",
            "description": violation.get("description", violation["rule"]),
        }
        for violation in violations
    ]
    return {
        "artifact_type": "robustness_gate_bias_report",
        "source_normative": "SOP 05; SOP 13; DN-030; DN-043",
        "status": status,
        "violations": violations,
        "incidents": incidents,
    }
