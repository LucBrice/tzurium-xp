"""Honest computation of the five economic-gate booleans from a SimulationResult.

Source: SOP 08 section 19; SOP 09B sections 16, 17, and 32; DN-023, DN-024,
DN-028, DN-029. Relocated from
Implementation/examples/controlled_experiments/gate_discrimination_experiment.py
(fix PLAN_CORRECTION_GATE_ECONOMIQUE_CALIBRATION) so that both the
production package builder and the controlled experiment share a single
computation, instead of the production path hardcoding all five booleens to
True.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from ebta_engine.strategy_api.contracts import SimulationResult

REQUIRED_ECONOMIC_THRESHOLDS = ("minimum_mean_return", "maximum_drawdown")
OPTIONAL_ECONOMIC_THRESHOLDS = ("maximum_total_costs",)


def compute_economic_pass_flags(
    result: SimulationResult,
    *,
    thresholds: dict[str, float],
) -> dict[str, bool]:
    """Compute the five booleans consumed by economic_gate_report().

    capacity_pass and execution_pass are not yet calibrated at the current
    MVP research scope (no production target_capital or execution stress
    grid has been provided) and are documented constants, per the 2026-07-10
    calibration decision — not silently invented thresholds.

    costs_pass: if "maximum_total_costs" is not provided in thresholds, it is
    derived from the net-of-costs return rather than an arbitrary absolute
    cap (2026-07-10 decision: daily_returns are already net of costs, so a
    candidate whose costs erase its edge already fails return_hurdle_pass).
    """
    missing = [key for key in REQUIRED_ECONOMIC_THRESHOLDS if key not in thresholds]
    if missing:
        raise ValueError(f"missing economic thresholds: {missing}")
    mean_return = _mean(result.daily_returns)
    max_drawdown = _max_drawdown(result.nav)
    return_hurdle_pass = mean_return >= float(thresholds["minimum_mean_return"])
    if "maximum_total_costs" in thresholds:
        costs_pass = result.total_costs <= float(thresholds["maximum_total_costs"])
    else:
        costs_pass = return_hurdle_pass
    return {
        "return_hurdle_pass": return_hurdle_pass,
        "drawdown_pass": max_drawdown <= float(thresholds["maximum_drawdown"]),
        "capacity_pass": True,
        "costs_pass": costs_pass,
        "execution_pass": True,
    }


def economic_observed_values(result: SimulationResult) -> dict[str, float]:
    """Return the scalar observations used to justify economic pass flags."""
    return {
        "mean_return": _mean(result.daily_returns),
        "total_costs": result.total_costs,
        "max_drawdown": _max_drawdown(result.nav),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _max_drawdown(nav: list[float]) -> float:
    if not nav:
        raise ValueError("nav must not be empty")
    peak = nav[0]
    max_drawdown = 0.0
    for value in nav:
        if value <= 0:
            return float("inf")
        if value > peak:
            peak = value
        max_drawdown = max(max_drawdown, (peak - value) / peak)
    return max_drawdown
