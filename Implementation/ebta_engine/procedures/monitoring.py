"""Sequential monitoring for incubation and live trading.

Source: SOP 11 sections 3, 13, 15, 20, 28, and 38; DN-037.
Type: IMPLEMENTATION_DETAIL.

DN-037: the statistical monitoring plan must follow a calendar schedule or a
preregistered sequential procedure that controls the number of consultations
(alpha-spending or equivalent stopping rule).  Opportunistic looks and
uncontrolled repeated testing are forbidden.

This module validates the monitoring plan structure and consultation log.
It does NOT implement the alpha-spending function itself; that computation
is performed by the backtesting engine and submitted here for validation.
"""

from __future__ import annotations

from typing import Any

# Allowed monitoring types (must match incubation_plan.schema.json).
_VALID_MONITORING_TYPES = frozenset({
    "CALENDAR_SCHEDULE",
    "SEQUENTIAL_PROCEDURE",
    "HYBRID",
})


def validate_monitoring_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate that a monitoring plan satisfies EBTA DN-037 requirements.

    Parameters
    ----------
    plan:
        Monitoring plan dict, compatible with the ``monitoring`` section of
        ``incubation_plan.schema.json``.

    Returns
    -------
    dict
        ``status``: PASS | FAIL | INCONCLUSIVE
    """
    if not plan:
        return _monitoring_result(
            "INCONCLUSIVE",
            violations=[{
                "rule": "DN-037_PLAN_REQUIRED",
                "description": "No monitoring plan provided.",
            }],
        )

    violations: list[dict[str, Any]] = []
    monitoring_type = str(plan.get("type", "")).upper()

    if monitoring_type not in _VALID_MONITORING_TYPES:
        violations.append({
            "rule": "DN-037_VALID_TYPE_REQUIRED",
            "authority": "SOP 11 / DN-037",
            "found": monitoring_type,
            "expected_one_of": sorted(_VALID_MONITORING_TYPES),
            "description": "Monitoring type must be CALENDAR_SCHEDULE, SEQUENTIAL_PROCEDURE, or HYBRID.",
        })

    if not plan.get("schedule_or_procedure"):
        violations.append({
            "rule": "DN-037_SCHEDULE_REQUIRED",
            "authority": "SOP 11 / DN-037",
            "description": "schedule_or_procedure must be defined.",
        })

    # Sequential procedures require an alpha-spending function.
    if monitoring_type in {"SEQUENTIAL_PROCEDURE", "HYBRID"}:
        if not plan.get("alpha_spending_function"):
            violations.append({
                "rule": "DN-037_ALPHA_SPENDING_REQUIRED",
                "authority": "SOP 11 / DN-037",
                "description": (
                    "SEQUENTIAL_PROCEDURE monitoring requires a preregistered "
                    "alpha-spending function (e.g., O'Brien-Fleming, Pocock). "
                    "Without it, repeated consultations constitute uncontrolled "
                    "multiple testing."
                ),
            })

    return _monitoring_result("PASS" if not violations else "FAIL", violations=violations)


def validate_consultation_log(
    consultations: list[dict[str, Any]],
    *,
    max_consultations: int | None = None,
    alpha_spending_function: str | None = None,
) -> dict[str, Any]:
    """Validate a consultation log against the preregistered monitoring plan.

    Parameters
    ----------
    consultations:
        Ordered list of monitoring consultation events.  Each dict must
        contain:
        - ``consultation_id`` (str)
        - ``timestamp`` (str, ISO-8601)
        - ``cumulative_alpha_spent`` (float, optional but required for
          sequential procedures)
        - ``consultation_verdict`` (str: WATCH | PASS | FAIL | INCONCLUSIVE)
        - ``repair_attempted`` (bool): must always be False
        - ``reselection_attempted`` (bool): must always be False

    max_consultations:
        Maximum allowed number of consultations per the preregistered plan.

    alpha_spending_function:
        Name of the preregistered alpha-spending function, if any.

    Returns
    -------
    dict
        ``status``: PASS | FAIL | INCONCLUSIVE
    """
    if not consultations:
        return _monitoring_result("INCONCLUSIVE", violations=[])

    violations: list[dict[str, Any]] = []

    # Check maximum consultations limit.
    if max_consultations is not None and len(consultations) > max_consultations:
        violations.append({
            "rule": "DN-037_MAX_CONSULTATIONS_EXCEEDED",
            "authority": "SOP 11 / DN-037",
            "max_allowed": max_consultations,
            "actual_count": len(consultations),
            "description": (
                "Number of monitoring consultations exceeds the preregistered "
                "maximum. Additional consultations constitute uncontrolled "
                "multiple testing."
            ),
        })

    for consultation in consultations:
        consultation_id = consultation.get("consultation_id", "<unknown>")

        # Alpha tracking for sequential procedures.
        if alpha_spending_function:
            cumulative = consultation.get("cumulative_alpha_spent")
            if cumulative is None:
                violations.append({
                    "rule": "DN-037_ALPHA_TRACKING_REQUIRED",
                    "authority": "SOP 11 / DN-037",
                    "consultation_id": consultation_id,
                    "description": (
                        "Sequential monitoring requires cumulative_alpha_spent "
                        "to be reported at each consultation."
                    ),
                })
            elif not isinstance(cumulative, (int, float)) or cumulative < 0 or cumulative > 1:
                violations.append({
                    "rule": "DN-037_ALPHA_BOUNDS",
                    "authority": "SOP 11 / DN-037",
                    "consultation_id": consultation_id,
                    "description": "cumulative_alpha_spent must be in [0, 1].",
                })

        # No repair or reselection allowed during monitoring.
        if consultation.get("repair_attempted"):
            violations.append({
                "rule": "DN-037_NO_MONITORING_REPAIR",
                "authority": "SOP 11 / DN-037",
                "consultation_id": consultation_id,
                "description": (
                    "Consultation flags repair_attempted=True. "
                    "Monitoring must not trigger alpha repair."
                ),
            })

        if consultation.get("reselection_attempted"):
            violations.append({
                "rule": "DN-037_NO_MONITORING_RESELECTION",
                "authority": "SOP 11 / DN-037",
                "consultation_id": consultation_id,
                "description": (
                    "Consultation flags reselection_attempted=True. "
                    "Monitoring must not trigger reselection of the model."
                ),
            })

    return _monitoring_result(
        "PASS" if not violations else "FAIL",
        violations=violations,
        consultation_count=len(consultations),
    )


def _monitoring_result(
    status: str,
    *,
    violations: list[dict[str, Any]],
    consultation_count: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "artifact_type": "monitoring_report",
        "source_normative": "SOP 11 sections 3, 13, 15, 20, 28, 38; DN-037",
        "status": status,
        "violations": violations,
    }
    if consultation_count is not None:
        result["consultation_count"] = consultation_count
    return result
