"""Pre-OOS package sealing checks.

Source: SOP 10 sections 5 and 6; SOP 12 section 3; DN-038.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone


def validate_pre_oos_seal(
    package_stage: str,
    *,
    manifest_hash: str,
    independent_approval: bool,
    clock: Callable[[], datetime] | None = None,
) -> dict:
    violations = []
    if package_stage != "PRE_OOS_SEALED":
        violations.append("package_not_pre_oos_sealed")
    if not manifest_hash:
        violations.append("missing_manifest_hash")
    if not independent_approval:
        violations.append("missing_independent_approval")
    report = {
        "artifact_type": "sealing_report",
        "status": "PASS" if not violations else "FAIL",
        "violations": violations,
    }
    if violations:
        return report

    sealed_at = (clock or _utc_now)()
    if sealed_at.tzinfo is None or sealed_at.utcoffset() is None:
        raise ValueError("sealing clock must return a timezone-aware datetime")
    report["sealed_at"] = sealed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    report["sealed_at_source"] = "INJECTED_FIXTURE_CLOCK" if clock is not None else "RUNTIME_UTC"
    return report


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
