"""OOS access authorization and log entry construction.

Source: SOP 10 sections 5, 7, 8, 29, and 30; DN-032, DN-033.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any


def authorize_oos_access(request: dict[str, Any]) -> dict[str, Any]:
    required_flags = [
        "pre_oos_sealed",
        "wrc_pass",
        "robustness_pass",
        "execution_pass",
        "independent_approval",
        "bias_gate_pass",
    ]
    missing = [flag for flag in required_flags if not request.get(flag)]
    status = "AUTHORIZED" if not missing else "DENIED"
    return {
        "artifact_type": "oos_access_decision",
        "status": status,
        "missing_requirements": missing,
        "log_entry": None if missing else _log_entry(request),
    }


def _log_entry(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "access_event_id": request["access_event_id"],
        "timestamp": request["timestamp"],
        "actor": request["actor"],
        "fold_id": request["fold_id"],
        "oos_segment_id": request["oos_segment_id"],
        "access_reason": request.get("access_reason", "authorized_oos_execution"),
    }
