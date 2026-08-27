"""Point-in-time data availability checks.

Source: SOP 09A sections 2, 4, 26, and 31; DN-025.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def validate_availability(decision_events: list[dict[str, str]]) -> dict[str, Any]:
    violations = []
    for event in decision_events:
        available_at = _parse_timestamp(event["available_at"])
        decision_at = _parse_timestamp(event["decision_at"])
        if available_at > decision_at:
            violations.append(event)
    return {
        "artifact_type": "data_availability_report",
        "status": "PASS" if not violations else "FAIL",
        "checked_count": len(decision_events),
        "violations": violations,
    }


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

