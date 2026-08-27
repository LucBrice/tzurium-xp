"""Separate economic gate helpers.

Source: SOP 08 section 19; SOP 09B sections 16, 17, and 32; DN-023, DN-024,
DN-028, DN-029.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any


def economic_gate_report(evidence: dict[str, Any]) -> dict[str, Any]:
    failures = []
    for key in ["return_hurdle_pass", "drawdown_pass", "capacity_pass", "costs_pass", "execution_pass"]:
        if evidence.get(key) is not True:
            failures.append(key)
    thresholds = evidence.get("thresholds", {})
    observed_values = evidence.get("observed_values", {})
    capacity_grid = evidence.get("capacity_grid", [])
    if not thresholds:
        failures.append("thresholds")
    if not observed_values:
        failures.append("observed_values")
    if not capacity_grid:
        failures.append("capacity_grid")
    economic_status = "PASS" if not failures else "REJECTED_ECONOMIC"
    statistical_status = evidence.get("statistical_status", "INCONCLUSIVE")
    if statistical_status == "PASS" and economic_status == "REJECTED_ECONOMIC":
        global_status = "REJECTED_ECONOMIC"
    elif statistical_status == "PASS" and economic_status == "PASS":
        global_status = "PASS"
    else:
        global_status = statistical_status
    return {
        "artifact_type": "economic_gate_report",
        "statistical_status": statistical_status,
        "economic_status": economic_status,
        "global_status": global_status,
        "failures": failures,
        "thresholds": thresholds,
        "observed_values": observed_values,
        "capacity_grid": capacity_grid,
    }
