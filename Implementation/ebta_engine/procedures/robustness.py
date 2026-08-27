"""Pre-OOS robustness gate and post-OOS diagnostic helpers.

Source: SOP 05 sections 5, 17, 19, 21, 23, and 29; DN-030, DN-031.
Type: IMPLEMENTATION_DETAIL.

The EBTA protocol distinguishes two distinct uses of robustness:

1. **Pre-OOS robustness** (DN-030): stress-tests that are preregistered and
   executed *before* opening each OOS_k.  The verdict may block OOS opening.
   Scenarios must be classified as CENTRAL, PLAUSIBLE_BASE, or EXTREME and
   cannot use observed OOS data.

2. **Post-OOS diagnostics** (DN-031): analyses run *after* OOS observation for
   descriptive and attribution purposes only.  They grant NO right to repair,
   reselect, or attempt a second run on the same data.

This module validates both use-cases without implementing the underlying
stress-test calculations (those belong to the backtesting engine).
"""

from __future__ import annotations

from typing import Any

# Allowed scenario classifications (SOP 05 / DN-030).
_VALID_CLASSIFICATIONS = frozenset({"CENTRAL", "PLAUSIBLE_BASE", "EXTREME"})

# Scenario verdict values that count as passing a blocking test.
_PASS_VERDICTS = frozenset({"PASS", "PASS_WITH_WARNING"})


# ---------------------------------------------------------------------------
# Pre-OOS robustness gate (primary use — may block OOS opening)
# ---------------------------------------------------------------------------


def pre_oos_robustness_verdict(
    scenarios: list[dict[str, Any]],
    *,
    preregistered_catalogue: list[str] | None = None,
) -> dict[str, Any]:
    """Validate a pre-OOS robustness scenario set.

    Parameters
    ----------
    scenarios:
        List of scenario result dicts.  Each dict must contain at minimum:
        - ``stress_id`` (str): unique identifier matching the preregistered
          plan.
        - ``classification`` (str): one of CENTRAL, PLAUSIBLE_BASE, EXTREME.
        - ``scenario_verdict`` (str): verdict produced by the backtester.
        - ``blocking`` (bool): True if a non-PASS verdict blocks OOS opening.
        - ``uses_observed_oos`` (bool): must always be False here.
        - ``influential_variant`` (bool, optional): True if the scenario
          changed the decision materially (required for audit trail).

    preregistered_catalogue:
        Optional list of stress_ids that were declared in the robustness plan
        before OOS.  If provided, missing scenarios are flagged as violations.

    Returns
    -------
    dict
        ``status``: PASS | FAIL | INCONCLUSIVE
    """
    if not scenarios:
        return _robustness_result(
            "INCONCLUSIVE",
            scenario_count=0,
            violations=[{
                "rule": "DN-030_PREREGISTERED_PLAN_REQUIRED",
                "description": "No scenarios provided; a pre-OOS robustness plan must exist.",
            }],
            phase="PRE_OOS",
            executed_stress_ids=[],
        )

    violations: list[dict[str, Any]] = []

    # Check coverage against preregistered catalogue.
    if preregistered_catalogue is not None:
        executed_ids = {s.get("stress_id") for s in scenarios}
        missing = sorted(set(preregistered_catalogue) - executed_ids)
        if missing:
            violations.append({
                "rule": "DN-030_CATALOGUE_COVERAGE",
                "authority": "SOP 05 / DN-030",
                "missing_stress_ids": missing,
                "description": (
                    "Preregistered stress-tests were not executed. All "
                    "scenarios in the preregistered catalogue must be run or "
                    "explicitly justified as non-applicable."
                ),
            })

    classification_counts: dict[str, int] = {
        "CENTRAL": 0, "PLAUSIBLE_BASE": 0, "EXTREME": 0,
    }

    for scenario in scenarios:
        stress_id = scenario.get("stress_id", "<unknown>")
        classification = str(scenario.get("classification", "")).upper()
        verdict = str(scenario.get("scenario_verdict", ""))
        blocking = bool(scenario.get("blocking", False))
        uses_oos = bool(scenario.get("uses_observed_oos", False))

        # Rule: classification must be one of the three canonical values.
        if classification not in _VALID_CLASSIFICATIONS:
            violations.append({
                "rule": "DN-030_CLASSIFICATION_REQUIRED",
                "authority": "SOP 05 / DN-030",
                "stress_id": stress_id,
                "found": classification,
                "expected_one_of": sorted(_VALID_CLASSIFICATIONS),
                "description": (
                    "Every pre-OOS scenario must be classified as CENTRAL, "
                    "PLAUSIBLE_BASE, or EXTREME."
                ),
            })
        else:
            classification_counts[classification] += 1

        # Rule: pre-OOS robustness must never use observed OOS (DN-030).
        if uses_oos:
            violations.append({
                "rule": "DN-030_NO_OBSERVED_OOS",
                "authority": "SOP 05 / DN-030",
                "stress_id": stress_id,
                "description": (
                    "Pre-OOS robustness check uses observed OOS data. This "
                    "violates DN-030: decision robustness must not rely on "
                    "any OOS_k already opened."
                ),
            })

        # Rule: blocking scenario must PASS or OOS stays closed.
        if blocking and verdict not in _PASS_VERDICTS:
            violations.append({
                "rule": "DN-030_BLOCKING_SCENARIO_FAILS",
                "authority": "SOP 05 / DN-030",
                "stress_id": stress_id,
                "classification": classification,
                "scenario_verdict": verdict,
                "description": (
                    "A blocking pre-OOS scenario did not PASS. OOS_k must "
                    "not be opened until this scenario passes or the plan is "
                    "revised via a preregistered override rule."
                ),
            })

    return _robustness_result(
        "PASS" if not violations else "FAIL",
        scenario_count=len(scenarios),
        violations=violations,
        phase="PRE_OOS",
        classification_counts=classification_counts,
        influential_variants=[
            s.get("stress_id")
            for s in scenarios
            if s.get("influential_variant")
        ],
        executed_stress_ids=[
            s.get("stress_id")
            for s in scenarios
            if s.get("stress_id")
        ],
    )


# ---------------------------------------------------------------------------
# Post-OOS diagnostic report (descriptive only — no repair rights)
# ---------------------------------------------------------------------------


def post_oos_diagnostic_report(
    scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """Produce a post-OOS robustness diagnostic report.

    DN-031: after OOS observation, robustness analyses are descriptive.
    They grant NO right to repair, reselect, or attempt a second run.
    This function validates that the submitted diagnostic respects those
    constraints.

    Parameters
    ----------
    scenarios:
        Post-OOS diagnostic scenario dicts.  Each must carry
        ``diagnostic_only: true`` to signal it is not being used as a gate.
    """
    if not scenarios:
        return _robustness_result(
            "INCONCLUSIVE",
            scenario_count=0,
            violations=[],
            phase="POST_OOS_DIAGNOSTIC",
            executed_stress_ids=[],
        )

    violations: list[dict[str, Any]] = []

    for scenario in scenarios:
        stress_id = scenario.get("stress_id", "<unknown>")
        diagnostic_only = bool(scenario.get("diagnostic_only", False))
        repair_attempted = bool(scenario.get("repair_attempted", False))
        reselection_attempted = bool(scenario.get("reselection_attempted", False))

        if not diagnostic_only:
            violations.append({
                "rule": "DN-031_DIAGNOSTIC_FLAG_REQUIRED",
                "authority": "SOP 05 / DN-031",
                "stress_id": stress_id,
                "description": (
                    "Post-OOS scenario is missing 'diagnostic_only: true'. "
                    "All post-OOS robustness analyses must be explicitly "
                    "flagged as descriptive."
                ),
            })

        if repair_attempted:
            violations.append({
                "rule": "DN-031_NO_REPAIR",
                "authority": "SOP 05 / DN-031",
                "stress_id": stress_id,
                "description": (
                    "Post-OOS diagnostic sets 'repair_attempted: true'. "
                    "Repair is forbidden after OOS observation (DN-031)."
                ),
            })

        if reselection_attempted:
            violations.append({
                "rule": "DN-031_NO_RESELECTION",
                "authority": "SOP 05 / DN-031",
                "stress_id": stress_id,
                "description": (
                    "Post-OOS diagnostic sets 'reselection_attempted: true'. "
                    "Reselection after OOS observation is forbidden (DN-031)."
                ),
            })

    return _robustness_result(
        "PASS" if not violations else "FAIL",
        scenario_count=len(scenarios),
        violations=violations,
        phase="POST_OOS_DIAGNOSTIC",
        executed_stress_ids=[
            s.get("stress_id")
            for s in scenarios
            if s.get("stress_id")
        ],
    )


# ---------------------------------------------------------------------------
# Legacy shim — kept for backward compatibility with existing tests
# ---------------------------------------------------------------------------


def robustness_verdict(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """Backward-compatible shim; prefer pre_oos_robustness_verdict().

    Routes to pre_oos_robustness_verdict() without a preregistered
    catalogue so existing tests and fixtures remain valid.
    """
    return pre_oos_robustness_verdict(scenarios, preregistered_catalogue=None)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _robustness_result(
    status: str,
    *,
    scenario_count: int,
    violations: list[dict[str, Any]],
    phase: str,
    classification_counts: dict[str, int] | None = None,
    influential_variants: list[str | None] | None = None,
    executed_stress_ids: list[str | None] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "artifact_type": "robustness_report",
        "source_normative": "SOP 05 sections 5, 17, 19, 21, 23, 29; DN-030, DN-031",
        "phase": phase,
        "scenario_count": scenario_count,
        "status": status,
        "violations": violations,
    }
    if classification_counts is not None:
        result["classification_counts"] = classification_counts
    if influential_variants is not None:
        result["influential_variants"] = [v for v in influential_variants if v]
    if executed_stress_ids is not None:
        result["executed_stress_ids"] = [stress_id for stress_id in executed_stress_ids if stress_id]
    return result
