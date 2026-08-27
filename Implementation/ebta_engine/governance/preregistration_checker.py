"""Preregistration lock checks for EBTA G-BIAS.

Source: SOP 13; SOP 03; SOP 08; PAQUET D'EXECUTION EBTA.md.
Type: CONTRACT_ENCODING.
"""

from __future__ import annotations

from typing import Any


DECISION_FIELDS = (
    "primary_metric",
    "secondary_metrics",
    "economic_hurdle",
    "benchmark",
    "cost_model",
    "slippage_model",
    "execution_assumptions",
)


def check_preregistration_lock(
    preregistered: dict[str, Any],
    executed: dict[str, Any],
    *,
    fields: tuple[str, ...] = DECISION_FIELDS,
) -> dict[str, Any]:
    """Compare preregistered and executed decision fields."""
    if not preregistered or not executed:
        return _report("INCONCLUSIVE", [{"rule": "PREREGISTRATION_EVIDENCE_MISSING"}])

    violations: list[dict[str, Any]] = []
    for field in fields:
        expected = _lookup(preregistered, field)
        observed = _lookup(executed, field)
        if expected is None or observed is None:
            violations.append({
                "rule": "PREREGISTERED_FIELD_MISSING",
                "field": field,
                "bias_id": "BIAS-003",
                "description": f"Missing preregistered or executed value for {field}.",
            })
        elif expected != observed:
            violations.append({
                "rule": "PREREGISTERED_FIELD_CHANGED",
                "field": field,
                "expected": expected,
                "observed": observed,
                "bias_id": _bias_for_field(field),
                "description": f"Decision field {field} changed after preregistration.",
            })
    return _report("PASS" if not violations else "FAIL", violations)


def _lookup(payload: dict[str, Any], field: str) -> Any:
    if field in payload:
        return payload[field]
    for section in ("selection_rule", "candidate_space", "execution_model", "economic_gate", "statistical_plan"):
        value = payload.get(section)
        if isinstance(value, dict) and field in value:
            return value[field]
    return None


def _bias_for_field(field: str) -> str:
    if field in {"primary_metric", "secondary_metrics"}:
        return "BIAS-007"
    if field == "benchmark":
        return "BIAS-008"
    if field == "economic_hurdle":
        return "BIAS-009"
    if field in {"cost_model", "slippage_model", "execution_assumptions"}:
        return "BIAS-019"
    return "BIAS-003"


def _report(status: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_type": "preregistration_lock_report",
        "source_normative": "SOP 13; SOP 03; SOP 08",
        "status": status,
        "violations": violations,
    }
