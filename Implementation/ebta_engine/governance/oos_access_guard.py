"""OOS access guard including G-BIAS precondition."""

from __future__ import annotations

from typing import Any


REQUIRED_PRE_OOS_FLAGS = (
    "pre_oos_sealed",
    "code_hash_frozen",
    "data_hash_frozen",
    "config_frozen",
    "wrc_pass",
    "robustness_pass",
    "registry_complete",
    "bias_gate_pass",
    "reviewer_registered",
)


def guard_oos_access(request: dict[str, Any]) -> dict[str, Any]:
    """Authorize, deny, or burn OOS access under SOP 10 and SOP 13."""
    if request.get("unauthorized_access_detected") or request.get("oos_state") == "BURNED":
        incident = _incident("BIAS-014", "LEVEL_4", "BURNED", "MARK_OOS_BURNED")
        return _report("BURNED", ["unauthorized_oos_access"], [incident])

    missing = [flag for flag in REQUIRED_PRE_OOS_FLAGS if not request.get(flag)]
    if request.get("open_blocking_incidents"):
        missing.append("no_open_level_2_or_higher_incident")
    if missing:
        incident = _incident("BIAS-015", "LEVEL_2", "OPEN", "DENY_OOS_UNTIL_G_BIAS_PASS")
        return _report("DENIED", missing, [incident])
    return _report("AUTHORIZED", [], [])


def _incident(bias_id: str, severity: str, status: str, decision: str) -> dict[str, Any]:
    return {
        "bias_id": bias_id,
        "severity": severity,
        "status": status,
        "decision": decision,
        "evidence_path": "oos_access_log.jsonl",
    }


def _report(status: str, missing: list[str], incidents: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_type": "oos_access_guard",
        "source_normative": "SOP 10; SOP 13; DN-032; DN-043; DN-046",
        "status": status,
        "missing_requirements": missing,
        "incidents": incidents,
    }
