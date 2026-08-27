"""Pre-OOS robustness scenario calculation.

Source: SOP 05 sections 5, 13, 17, 19, and 23.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any

from ebta_engine.strategy_api.contracts import SimulationResult


VALID_CLASSIFICATIONS = frozenset({"CENTRAL", "PLAUSIBLE_BASE", "EXTREME"})


def compute_robustness_scenarios(
    results_by_scenario: dict[str, list[SimulationResult]],
    *,
    scenario_grid: dict[str, Any],
) -> list[dict[str, Any]]:
    """Produce scenario rows consumed by procedures.robustness.

    The thresholds and blocking flags must come from the preregistered
    scenario_grid. This function derives verdict inputs from Test-side
    SimulationResult objects; it does not decide the robustness gate.
    """
    scenarios = scenario_grid.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenario_grid must define a non-empty scenarios list")

    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        stress_id = str(scenario.get("stress_id", ""))
        classification = str(scenario.get("classification", "")).upper()
        if not stress_id:
            raise ValueError("scenario stress_id is required")
        if classification not in VALID_CLASSIFICATIONS:
            raise ValueError(f"invalid robustness classification for {stress_id}: {classification}")
        results = results_by_scenario.get(stress_id)
        if not results:
            rows.append(_row(stress_id, classification, "INCONCLUSIVE", scenario, mean_return=None))
            continue

        all_returns = [value for result in results for value in result.daily_returns]
        mean_return = sum(all_returns) / len(all_returns) if all_returns else 0.0
        minimum_mean_return = scenario.get("minimum_mean_return")
        maximum_total_costs = scenario.get("maximum_total_costs")
        if minimum_mean_return is None and maximum_total_costs is None:
            scenario_verdict = "INCONCLUSIVE"
        elif minimum_mean_return is not None and mean_return < float(minimum_mean_return):
            scenario_verdict = "REJECTED_ECONOMIC"
        elif maximum_total_costs is not None and sum(result.total_costs for result in results) > float(maximum_total_costs):
            scenario_verdict = "REJECTED_ECONOMIC"
        else:
            scenario_verdict = "PASS"
        rows.append(_row(stress_id, classification, scenario_verdict, scenario, mean_return=mean_return))
    return rows


def _row(
    stress_id: str,
    classification: str,
    scenario_verdict: str,
    scenario: dict[str, Any],
    *,
    mean_return: float | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "stress_id": stress_id,
        "classification": classification,
        "scenario_verdict": scenario_verdict,
        "blocking": bool(scenario.get("blocking", False)),
        "uses_observed_oos": False,
        "influential_variant": bool(scenario.get("influential_variant", False)),
    }
    if mean_return is not None:
        row["mean_return"] = mean_return
    if "stress_family" in scenario:
        row["stress_family"] = scenario["stress_family"]
    return row
