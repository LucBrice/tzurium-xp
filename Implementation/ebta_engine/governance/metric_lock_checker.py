"""Metric, hurdle, benchmark, and cost lock checker for G-BIAS."""

from __future__ import annotations

from typing import Any

from .preregistration_checker import DECISION_FIELDS, check_preregistration_lock


def check_metric_lock(
    preregistered_config: dict[str, Any],
    executed_config: dict[str, Any],
) -> dict[str, Any]:
    """Fail if decision metrics, hurdles, benchmarks, or costs changed."""
    report = check_preregistration_lock(preregistered_config, executed_config, fields=DECISION_FIELDS)
    incidents = []
    for violation in report["violations"]:
        incidents.append({
            "bias_id": violation.get("bias_id", "BIAS-007"),
            "severity": "LEVEL_2",
            "status": "OPEN",
            "decision": "FAIL_G_BIAS_AND_RESTORE_PREREGISTERED_DECISION_FIELD",
            "evidence_path": "config.json",
            "description": violation.get("description", violation["rule"]),
        })
    return {
        "artifact_type": "metric_lock_report",
        "source_normative": "SOP 13; SOP 08; DN-042 to DN-047",
        "status": report["status"],
        "violations": report["violations"],
        "incidents": incidents,
    }
