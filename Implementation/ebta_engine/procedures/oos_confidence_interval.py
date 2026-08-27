"""OOS confidence interval procedure.

Source: SOP 01 sections 3, 4, 7, 8, 10, 13, 15, and 20; DN-019 to DN-022.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

import math
import statistics
from statistics import NormalDist
from typing import Any

from ebta_engine.procedures.bootstrap import stationary_block_indices


def oos_confidence_interval(
    oos_returns: list[float],
    *,
    replications: int,
    mean_block_length: float,
    seed: int,
    pre_oos_development_returns: list[float],
    min_annualized_return: float,
    bootstrap_source: str = "OOS_STATIONARY_BLOCK",
    target_power: float = 0.80,
    alpha: float = 0.05,
    sessions_per_year: int = 252,
) -> dict[str, Any]:
    if not oos_returns:
        raise ValueError("OOS confidence interval requires a non-empty OOS series")
    if "WRC" in bootstrap_source.upper() or "TEST" in bootstrap_source.upper():
        raise ValueError("OOS confidence interval must not reuse WRC Test bootstrap distribution")
    indices = stationary_block_indices(
        len(oos_returns),
        replications=replications,
        mean_block_length=mean_block_length,
        seed=seed,
    )
    bootstrap_means = [
        sum(oos_returns[index] for index in sample) / len(sample)
        for sample in indices
    ]
    estimate = sum(oos_returns) / len(oos_returns)
    lower_95 = _quantile(bootstrap_means, 0.05)
    upper_90 = _quantile(bootstrap_means, 0.95)
    power_check = achieved_power_check(
        pre_oos_development_returns,
        oos_observation_count=len(oos_returns),
        min_annualized_return=min_annualized_return,
        replications=replications,
        mean_block_length=mean_block_length,
        seed=seed,
        target_power=target_power,
        alpha=alpha,
        sessions_per_year=sessions_per_year,
    )
    achieved_power = power_check.get("achieved_power")
    verdict_power = achieved_power if isinstance(achieved_power, float) else 0.0
    verdict = _statistical_verdict(estimate, lower_95, verdict_power)
    return {
        "artifact_type": "oos_confidence_interval",
        "source_normative": "SOP 01 sections 3, 4, 7, 8, 10, 13, 15, 20; DN-019 to DN-022",
        "source": bootstrap_source,
        "oos_observation_count": len(oos_returns),
        "estimate": estimate,
        "lower_95_one_sided": lower_95,
        "upper_90_descriptive": upper_90,
        "ci_90_descriptive": [lower_95, upper_90],
        "annualized_log_estimate": sessions_per_year * estimate,
        "annualized_simple_estimate": math.exp(sessions_per_year * estimate) - 1.0,
        "bootstrap_means": bootstrap_means,
        "replications": replications,
        "seed": seed,
        "power": achieved_power,
        "power_check": power_check,
        "statistical_gate": verdict,
    }


def _quantile(values: list[float], probability: float) -> float:
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _statistical_verdict(estimate: float, lower_bound: float, power: float) -> str:
    if power < 0.80:
        return "INCONCLUSIVE"
    if estimate <= 0:
        return "FAIL"
    if lower_bound > 0:
        return "PASS"
    return "NOT_VALIDATED"


def validate_power_target(
    achieved_power: float,
    *,
    target_power: float = 0.80,
) -> dict[str, object]:
    """Validate that achieved power meets the preregistered target.

    Source: SOP 01; DN-021 — OOS analysis requires a target power of at
    least 80% per the preregistered plan.

    Parameters
    ----------
    achieved_power:
        Power estimate computed or supplied by the research pipeline.
    target_power:
        Preregistered minimum power target.  Defaults to 0.80 (DN-021).

    Returns
    -------
    dict
        ``status``: PASS | INCONCLUSIVE
    """
    if achieved_power >= target_power:
        return {
            "status": "PASS",
            "achieved_power": achieved_power,
            "target_power": target_power,
            "authority": "SOP 01 / DN-021",
        }
    return {
        "status": "INCONCLUSIVE",
        "achieved_power": achieved_power,
        "target_power": target_power,
        "authority": "SOP 01 / DN-021",
        "description": (
            f"Achieved power {achieved_power:.2f} is below the preregistered "
            f"target {target_power:.2f}. The OOS result is INCONCLUSIVE "
            "until the information stop criterion is met (DN-021)."
        ),
    }


def achieved_power_check(
    pre_oos_development_returns: list[float],
    *,
    oos_observation_count: int,
    min_annualized_return: float,
    replications: int,
    mean_block_length: float,
    seed: int,
    target_power: float = 0.80,
    alpha: float = 0.05,
    sessions_per_year: int = 252,
) -> dict[str, object]:
    """Estimate achieved power from pre-OOS development returns only.

    Source: SOP 01 section 10.6. The long-run variance estimate must be
    computed before OOS from development data; OOS returns are not an input.
    """
    base_payload: dict[str, object] = {
        "target_power": target_power,
        "authority": "SOP 01 / DN-021",
        "method": "PRE_OOS_STATIONARY_BLOCK_LONG_RUN_VARIANCE",
        "variance_source": "pre_oos_development_returns",
        "pre_oos_observation_count": len(pre_oos_development_returns),
        "oos_observation_count": oos_observation_count,
        "mean_block_length": mean_block_length,
        "replications": replications,
        "seed": seed,
        "alpha": alpha,
        "sessions_per_year": sessions_per_year,
        "min_annualized_return": min_annualized_return,
    }
    if min_annualized_return <= 0:
        return _inconclusive_power(base_payload, "min_annualized_return_must_be_positive")
    if sessions_per_year <= 0:
        return _inconclusive_power(base_payload, "sessions_per_year_must_be_positive")
    if oos_observation_count <= 0:
        return _inconclusive_power(base_payload, "oos_observation_count_must_be_positive")
    if len(pre_oos_development_returns) < 2:
        return _inconclusive_power(base_payload, "insufficient_pre_oos_observations")
    if mean_block_length <= 0:
        return _inconclusive_power(base_payload, "mean_block_length_must_be_positive")
    effective_blocks = math.floor(len(pre_oos_development_returns) / mean_block_length)
    base_payload["effective_pre_oos_blocks"] = effective_blocks
    if effective_blocks < 30:
        return _inconclusive_power(base_payload, "insufficient_distinct_pre_oos_blocks")

    indices = stationary_block_indices(
        len(pre_oos_development_returns),
        replications=replications,
        mean_block_length=mean_block_length,
        seed=seed,
    )
    bootstrap_means = [
        sum(pre_oos_development_returns[index] for index in sample) / len(sample)
        for sample in indices
    ]
    if len(bootstrap_means) < 2:
        return _inconclusive_power(base_payload, "insufficient_bootstrap_replications")
    pre_oos_mean_se = statistics.pstdev(bootstrap_means)
    if not math.isfinite(pre_oos_mean_se) or pre_oos_mean_se <= 0:
        return _inconclusive_power(base_payload, "non_positive_pre_oos_standard_error")

    daily_mde = math.log1p(min_annualized_return) / sessions_per_year
    long_run_std = pre_oos_mean_se * math.sqrt(len(pre_oos_development_returns))
    oos_mean_se = long_run_std / math.sqrt(oos_observation_count)
    if not math.isfinite(oos_mean_se) or oos_mean_se <= 0:
        return _inconclusive_power(base_payload, "non_positive_oos_standard_error")

    normal = NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha)
    z_effect = daily_mde / oos_mean_se
    achieved_power = min(1.0, max(0.0, normal.cdf(z_effect - z_alpha)))
    result = validate_power_target(achieved_power, target_power=target_power)
    result.update(
        {
            **base_payload,
            "achieved_power": achieved_power,
            "daily_minimum_detectable_effect": daily_mde,
            "pre_oos_mean_standard_error": pre_oos_mean_se,
            "long_run_standard_deviation": long_run_std,
            "oos_mean_standard_error": oos_mean_se,
            "z_alpha": z_alpha,
            "z_effect": z_effect,
        }
    )
    return result


def _inconclusive_power(base_payload: dict[str, object], reason: str) -> dict[str, object]:
    return {
        **base_payload,
        "status": "INCONCLUSIVE",
        "achieved_power": None,
        "reason": reason,
        "description": f"Achieved power cannot be estimated defensibly: {reason}.",
    }


def validate_information_stop_point(
    oos_observation_count: int,
    *,
    preregistered_stop_count: int | None = None,
    preregistered_stop_date: str | None = None,
    actual_date: str | None = None,
) -> dict[str, object]:
    """Verify that the verdict is computed at the preregistered stop point.

    Source: DN-004 — the OOS verdict must be produced at the preregistered
    information stop criterion, not opportunistically on significance.

    Parameters
    ----------
    oos_observation_count:
        Number of OOS observations in the current series.
    preregistered_stop_count:
        Preregistered number of OOS days at which to compute the verdict.
    preregistered_stop_date:
        Preregistered calendar date at which to compute the verdict.
    actual_date:
        Actual date of the verdict computation (ISO-8601 string).

    Returns
    -------
    dict
        ``status``: PASS | INCONCLUSIVE | FAIL
    """
    violations: list[str] = []

    if preregistered_stop_count is not None:
        if oos_observation_count < preregistered_stop_count:
            violations.append(
                f"OOS has {oos_observation_count} observations but the "
                f"preregistered stop requires {preregistered_stop_count}. "
                "The verdict must not be computed early (DN-004)."
            )

    if preregistered_stop_date is not None and actual_date is not None:
        if actual_date < preregistered_stop_date:
            violations.append(
                f"Verdict computed on {actual_date} before the preregistered "
                f"stop date {preregistered_stop_date}. "
                "Early stopping is only allowed by an independent rule (DN-004)."
            )

    return {
        "status": "PASS" if not violations else "FAIL",
        "oos_observation_count": oos_observation_count,
        "preregistered_stop_count": preregistered_stop_count,
        "preregistered_stop_date": preregistered_stop_date,
        "authority": "SOP 01 / DN-004",
        "violations": violations,
    }
