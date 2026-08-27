"""Walk-forward schedule checks.

Source: SOP 04 sections 3, 10, 11, 13, 17, 22, and 27; DN-001 to DN-004,
DN-027.
Type: IMPLEMENTATION_DETAIL.

DN-001: OOS segments are successive, non-overlapping, opened once, and
concatenated chronologically.
DN-002: No additional final holdout after the Walk-Forward global OOS.
DN-004: The verdict is calculated at the preregistered information stop
criterion; folds may not be added opportunistically based on results.
DN-027: Purge covers cross-segment dependencies; embargo handles residual
cases that are justified and prespecified.

This module adds a PREVENTIVE overlap check at schedule construction time,
complementing the post-hoc INV-001 invariant check.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def validate_walk_forward_schedule(
    folds: list[dict[str, Any]],
    *,
    information_stop_criterion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a Walk-Forward fold schedule.

    Parameters
    ----------
    folds:
        List of fold dicts.  Each fold must provide at minimum:
        - ``fold_id`` (str)
        - ``train`` ([start, end])
        - ``test`` ([start, end])
        - ``oos`` ([start, end])
        - ``purge_days`` (int)
        - ``embargo_days`` (int)
        - ``warmup_days`` (int)
        - ``policy`` (str: ROLLING | EXPANDING)
        - ``information_cutoff`` (str: ISO date)

    information_stop_criterion:
        Optional preregistered stop criterion dict (from the
        walk_forward_declaration.schema.json).  If provided, the schedule
        is checked against it to detect opportunistic fold additions (DN-004).

    Returns
    -------
    dict
        ``status``: PASS | FAIL | INCONCLUSIVE
    """
    violations: list[dict[str, Any]] = []

    # --- PREVENTIVE check: extract all OOS ranges first ---
    # This detects overlaps at schedule-construction time, BEFORE any fold
    # data is accessed (complement to post-hoc INV-001).
    oos_ranges: list[tuple[date, date, str]] = []
    for fold in folds:
        oos_start, oos_end = _date_range(fold["oos"])
        fold_id = fold.get("fold_id", "<unknown>")
        for prev_start, prev_end, prev_id in oos_ranges:
            if oos_start <= prev_end and prev_start <= oos_end:
                violations.append({
                    "rule": "DN-001_OOS_OVERLAP_PREVENTIVE",
                    "authority": "SOP 04 / DN-001 / INV-001",
                    "fold_id": fold_id,
                    "conflicts_with": prev_id,
                    "description": (
                        "OOS segments overlap detected at schedule construction "
                        "time. This would violate INV-001 and DN-001. Correct "
                        "the fold schedule before processing any data."
                    ),
                })
        oos_ranges.append((oos_start, oos_end, fold_id))

    # --- Per-fold structural checks ---
    previous_oos_end: date | None = None
    for fold in folds:
        fold_id = fold.get("fold_id", "<unknown>")
        train_start, train_end = _date_range(fold["train"])
        test_start, test_end = _date_range(fold["test"])
        oos_start, oos_end = _date_range(fold["oos"])

        # Segment ordering.
        if not (train_start <= train_end < test_start <= test_end < oos_start <= oos_end):
            violations.append({
                "rule": "SOP04_SEGMENT_ORDER",
                "authority": "SOP 04",
                "fold_id": fold_id,
                "description": "Segments are not in the required order: train < test < oos.",
            })

        # OOS must follow previous OOS chronologically (DN-001).
        if previous_oos_end is not None and oos_start <= previous_oos_end:
            violations.append({
                "rule": "DN-001_OOS_CHRONOLOGICAL",
                "authority": "SOP 04 / DN-001",
                "fold_id": fold_id,
                "description": (
                    "OOS segment does not start after the previous OOS end. "
                    "OOS segments must be chronological (DN-001)."
                ),
            })

        # Required fields.
        for field in ("purge_days", "embargo_days", "warmup_days"):
            if fold.get(field) is None:
                violations.append({
                    "rule": f"DN-027_FIELD_REQUIRED_{field.upper()}",
                    "authority": "SOP 04 / DN-027",
                    "fold_id": fold_id,
                    "description": f"Field '{field}' is required (DN-027).",
                })

        if not fold.get("policy"):
            violations.append({
                "rule": "SOP04_POLICY_REQUIRED",
                "authority": "SOP 04",
                "fold_id": fold_id,
                "description": "Field 'policy' (ROLLING or EXPANDING) is required.",
            })

        if not fold.get("information_cutoff"):
            violations.append({
                "rule": "DN-004_INFORMATION_CUTOFF_REQUIRED",
                "authority": "SOP 01 / DN-004",
                "fold_id": fold_id,
                "description": (
                    "Field 'information_cutoff' is required. The verdict must "
                    "be computed at a preregistered information stop point "
                    "and not selected opportunistically (DN-004)."
                ),
            })

        previous_oos_end = oos_end

    # --- Information stop criterion check (DN-004) ---
    if information_stop_criterion is not None:
        criterion_type = str(information_stop_criterion.get("criterion_type", "")).upper()
        if criterion_type == "FIXED_FOLD_COUNT":
            expected_count = information_stop_criterion.get("fixed_fold_count")
            if expected_count is not None and len(folds) > expected_count:
                violations.append({
                    "rule": "DN-004_FOLD_COUNT_EXCEEDED",
                    "authority": "SOP 01 / DN-004",
                    "expected": expected_count,
                    "actual": len(folds),
                    "description": (
                        "Fold count exceeds the preregistered FIXED_FOLD_COUNT "
                        "stop criterion. Additional folds may not be added "
                        "opportunistically based on observed results (DN-004)."
                    ),
                })

    return {
        "artifact_type": "fold_schedule_report",
        "source_normative": "SOP 04 sections 3, 10, 11, 13, 17, 22, 27; DN-001 to DN-004, DN-027",
        "status": "PASS" if not violations else "FAIL",
        "fold_count": len(folds),
        "violations": violations,
    }


def _date_range(values: list[str]) -> tuple[date, date]:
    return date.fromisoformat(values[0]), date.fromisoformat(values[1])
