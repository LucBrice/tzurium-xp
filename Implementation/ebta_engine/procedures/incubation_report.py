"""Incubation and deployment report helpers.

Source: SOP 11 sections 3, 13, 15, 20, 28, and 38; SOP 12 sections 3 and 38;
DN-035, DN-036, DN-037, DN-039.
Type: IMPLEMENTATION_DETAIL.

This module validates incubation and live deployment report structures.
It does NOT generate the underlying trading data; the backtesting or live
engine provides the report content and this module verifies its compliance
with the EBTA contract.
"""

from __future__ import annotations

from typing import Any

_VALID_INCUBATION_VERDICTS = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "WATCH"})
_VALID_LIFECYCLE_VERDICTS = frozenset({"PASS", "FAIL", "INCONCLUSIVE", "WATCH", "SUSPENDED"})


def validate_incubation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Validate a paper-trading incubation report.

    Source: SOP 11; DN-035; PAQUET D'EXECUTION section 4 (rapport d'incubation).

    Parameters
    ----------
    report:
        Incubation report dict.  Must contain at minimum:
        - ``report_id`` (str)
        - ``config_id`` (str)
        - ``package_stage`` (str): must be VALIDATION_READY or higher
        - ``paper_trading_days`` (int)
        - ``data_source_ids`` (list of str)
        - ``signal_log_hash`` (str)
        - ``execution_log_hash`` (str)
        - ``costs_applied`` (bool)
        - ``risk_monitored`` (bool)
        - ``incidents`` (list of dict)
        - ``verdict`` (str): PASS | FAIL | INCONCLUSIVE | WATCH
        - ``alpha_repair_attempted`` (bool): must be False

    Returns
    -------
    dict
        ``status``: PASS | FAIL | INCONCLUSIVE
    """
    if not report:
        return _incubation_result("INCONCLUSIVE", violations=[{
            "rule": "DN-035_REPORT_REQUIRED",
            "description": "Empty incubation report.",
        }])

    violations: list[dict[str, Any]] = []

    required_fields = [
        "report_id", "config_id", "package_stage", "paper_trading_days",
        "signal_log_hash", "execution_log_hash", "costs_applied",
        "risk_monitored", "incidents", "verdict",
    ]
    for field in required_fields:
        if field not in report:
            violations.append({
                "rule": "DN-035_FIELD_REQUIRED",
                "authority": "SOP 11 / DN-035",
                "field": field,
                "description": f"Required incubation report field '{field}' is missing.",
            })

    # Package stage must be VALIDATION_READY or higher (DN-039).
    package_stage = str(report.get("package_stage", ""))
    _valid_stages = {"VALIDATION_READY", "DEPLOYMENT_CERTIFIED", "LIFECYCLE_ARCHIVED"}
    if package_stage and package_stage not in _valid_stages:
        violations.append({
            "rule": "DN-039_VALIDATION_READY_REQUIRED",
            "authority": "SOP 12 / DN-039",
            "found": package_stage,
            "description": (
                "Incubation requires package_stage=VALIDATION_READY or higher. "
                "Incubation before VALIDATION_READY is forbidden (DN-039)."
            ),
        })

    # No alpha repair during incubation (DN-035).
    if report.get("alpha_repair_attempted"):
        violations.append({
            "rule": "DN-035_NO_ALPHA_REPAIR",
            "authority": "SOP 11 / DN-035",
            "description": (
                "Incubation report signals alpha_repair_attempted=True. "
                "Incubation verifies operationally; it must not repair alpha."
            ),
        })

    # Verdict must be valid.
    verdict = str(report.get("verdict", ""))
    if verdict and verdict not in _VALID_INCUBATION_VERDICTS:
        violations.append({
            "rule": "DN-035_VALID_VERDICT",
            "authority": "SOP 11 / DN-035",
            "found": verdict,
            "expected_one_of": sorted(_VALID_INCUBATION_VERDICTS),
            "description": "Incubation verdict must be one of PASS, FAIL, INCONCLUSIVE, WATCH.",
        })

    # Costs and risk must be monitored.
    if report.get("costs_applied") is False:
        violations.append({
            "rule": "DN-035_COSTS_REQUIRED",
            "authority": "SOP 11 / DN-035",
            "description": "costs_applied is False. All costs must be applied during incubation.",
        })

    if report.get("risk_monitored") is False:
        violations.append({
            "rule": "DN-035_RISK_MONITORING_REQUIRED",
            "authority": "SOP 11 / DN-035",
            "description": "risk_monitored is False. Risk must be actively monitored during incubation.",
        })

    return _incubation_result(
        "PASS" if not violations else "FAIL",
        violations=violations,
        paper_trading_days=report.get("paper_trading_days"),
        verdict=verdict,
        incident_count=len(report.get("incidents") or []),
    )


def validate_live_deployment_report(report: dict[str, Any]) -> dict[str, Any]:
    """Validate a live deployment report.

    Source: SOP 11; DN-036; PAQUET D'EXECUTION section 2 (G13 checklist).

    Parameters
    ----------
    report:
        Live deployment report dict.  Must contain:
        - ``report_id`` (str)
        - ``config_id`` (str)
        - ``package_stage`` (str): must be DEPLOYMENT_CERTIFIED
        - ``live_version_id`` (str)
        - ``capital_deployed`` (number)
        - ``capital_limit`` (number)
        - ``sizing_policy_applied`` (bool)
        - ``kill_switch_tested`` (bool)
        - ``monitoring_plan_id`` (str)
        - ``verdict`` (str)
    """
    if not report:
        return _incubation_result("INCONCLUSIVE", violations=[{
            "rule": "DN-036_REPORT_REQUIRED",
            "description": "Empty live deployment report.",
        }])

    violations: list[dict[str, Any]] = []

    required_fields = [
        "report_id", "config_id", "package_stage", "live_version_id",
        "capital_deployed", "capital_limit", "sizing_policy_applied",
        "kill_switch_tested", "monitoring_plan_id", "verdict",
    ]
    for field in required_fields:
        if field not in report:
            violations.append({
                "rule": "DN-036_FIELD_REQUIRED",
                "authority": "SOP 11 / DN-036",
                "field": field,
                "description": f"Required live deployment report field '{field}' is missing.",
            })

    # Package must be DEPLOYMENT_CERTIFIED (DN-040).
    stage = str(report.get("package_stage", ""))
    if stage and stage != "DEPLOYMENT_CERTIFIED":
        violations.append({
            "rule": "DN-040_DEPLOYMENT_CERTIFIED_REQUIRED",
            "authority": "SOP 12 / DN-040",
            "found": stage,
            "description": (
                "Live deployment requires package_stage=DEPLOYMENT_CERTIFIED. "
                "Live trading before this stage is forbidden (DN-040)."
            ),
        })

    # Capital must not exceed limit (DN-029).
    capital_deployed = report.get("capital_deployed")
    capital_limit = report.get("capital_limit")
    if (
        capital_deployed is not None
        and capital_limit is not None
        and capital_deployed > capital_limit
    ):
        violations.append({
            "rule": "DN-029_CAPITAL_EXCEEDS_LIMIT",
            "authority": "SOP 09B / DN-029",
            "capital_deployed": capital_deployed,
            "capital_limit": capital_limit,
            "description": (
                "capital_deployed exceeds capital_limit. "
                "Capital must not exceed the validated capacity level (DN-029)."
            ),
        })

    if report.get("kill_switch_tested") is False:
        violations.append({
            "rule": "DN-036_KILL_SWITCH_REQUIRED",
            "authority": "SOP 11 / DN-036",
            "description": "kill_switch_tested is False. Kill switch must be verified before live deployment.",
        })

    verdict = report.get("verdict")
    if verdict not in _VALID_LIFECYCLE_VERDICTS:
        violations.append({
            "rule": "DN-036_VALID_VERDICT",
            "authority": "SOP 11 / DN-036",
            "found": verdict,
            "expected_one_of": sorted(_VALID_LIFECYCLE_VERDICTS),
            "description": "Live deployment verdict is unknown.",
        })
    elif verdict != "PASS":
        violations.append({
            "rule": "DN-036_PASS_VERDICT_REQUIRED",
            "authority": "SOP 11 / DN-036",
            "found": verdict,
            "description": "Live deployment requires an exact PASS verdict.",
        })

    return _incubation_result(
        "PASS" if not violations else "FAIL",
        violations=violations,
        verdict=str(verdict or ""),
    )


def _incubation_result(
    status: str,
    *,
    violations: list[dict[str, Any]],
    paper_trading_days: int | None = None,
    verdict: str = "",
    incident_count: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "artifact_type": "incubation_report",
        "source_normative": "SOP 11; SOP 12; DN-035, DN-036, DN-037, DN-039, DN-040",
        "status": status,
        "violations": violations,
    }
    if paper_trading_days is not None:
        result["paper_trading_days"] = paper_trading_days
    if verdict:
        result["submitted_verdict"] = verdict
    if incident_count is not None:
        result["incident_count"] = incident_count
    return result
