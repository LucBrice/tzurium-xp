"""White's Reality Check and SOP 02 secondary analyses.

Source: SOP 02 sections 6, 7, 8, 9, 10, 11, 12, 14, 15, and 18.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Callable

from ebta_engine.procedures.bootstrap import resample_columns, stationary_block_indices
from ebta_engine.procedures.zero_centering import zero_center_columns


def wrc_test(
    candidate_series: dict[str, list[float]],
    *,
    replications: int,
    mean_block_length: float,
    seed: int,
    alpha: float = 0.05,
    run_secondary: bool = True,
    mcpm_permutation_scheme: dict | None = None,
    mcpm_recalculator: Callable[[dict[str, list[float]], list[int]], dict[str, list[float]]] | None = None,
) -> dict:
    _validate_matrix(candidate_series)
    if len(candidate_series) < 2:
        raise ValueError("WRC requires the complete applicable family, not only the selected winner")
    length = len(next(iter(candidate_series.values())))
    observed_statistic = _max_statistic(candidate_series)
    observed_candidate_statistics = _candidate_statistics(candidate_series)
    centered = zero_center_columns(candidate_series)["centered_series"]
    bootstrap_indices = stationary_block_indices(
        length,
        replications=replications,
        mean_block_length=mean_block_length,
        seed=seed,
    )
    distribution = [
        _max_statistic(resample_columns(centered, indices))
        for indices in bootstrap_indices
    ]
    exceedance_count = sum(1 for statistic in distribution if statistic >= observed_statistic)
    pvalue = (1 + exceedance_count) / (replications + 1)
    verdict = "PASS" if pvalue < alpha else "FAIL"
    secondary_tests = (
        _secondary_reports(
            candidate_series,
            centered,
            bootstrap_indices,
            observed_candidate_statistics,
            alpha,
            verdict,
            mcpm_permutation_scheme,
            mcpm_recalculator,
        )
        if run_secondary
        else _secondary_not_run()
    )
    return {
        "artifact_type": "wrc_report",
        "primary_test": "WRC",
        "source_normative": "SOP 02 sections 6-12; DN-008 to DN-011; DN-018",
        "candidate_ids": sorted(candidate_series),
        "family_catalogue_hash": _family_catalogue_hash(candidate_series),
        "observed_statistic": observed_statistic,
        "observed_candidate_statistics": observed_candidate_statistics,
        "bootstrap_distribution": distribution,
        "exceedance_count": exceedance_count,
        "wrc_pvalue": pvalue,
        "alpha": alpha,
        "verdict": verdict,
        "primary_gate_authority": "WRC_ONLY",
        "secondary_tests_cannot_override_wrc": True,
        "seed": seed,
        "replications": replications,
        "power_diagnostics": _power_diagnostics(candidate_series),
        "secondary_tests": secondary_tests,
    }


def _validate_matrix(candidate_series: dict[str, list[float]]) -> None:
    if not candidate_series:
        raise ValueError("WRC requires a non-empty matrix")
    lengths = {len(values) for values in candidate_series.values()}
    if len(lengths) != 1:
        raise ValueError("all WRC candidate series must share the same length")
    if next(iter(lengths)) == 0:
        raise ValueError("WRC series must not be empty")


def _max_statistic(candidate_series: dict[str, list[float]]) -> float:
    length = len(next(iter(candidate_series.values())))
    scale = math.sqrt(length)
    return max(scale * (sum(values) / length) for values in candidate_series.values())


def _candidate_statistics(candidate_series: dict[str, list[float]]) -> dict[str, float]:
    length = len(next(iter(candidate_series.values())))
    scale = math.sqrt(length)
    return {
        candidate_id: scale * (sum(values) / length)
        for candidate_id, values in sorted(candidate_series.items())
    }


def _studentized_statistics(candidate_series: dict[str, list[float]]) -> dict[str, float]:
    length = len(next(iter(candidate_series.values())))
    scale = math.sqrt(length)
    statistics = {}
    for candidate_id, values in sorted(candidate_series.items()):
        long_run_variance = _long_run_variance(values)
        denominator = math.sqrt(long_run_variance)
        statistics[candidate_id] = 0.0 if denominator == 0 else scale * (sum(values) / length) / denominator
    return statistics


def _long_run_variance(values: list[float]) -> float:
    """Small deterministic HAC-style variance estimator for Test_k reports."""
    length = len(values)
    mean = sum(values) / length
    centered = [value - mean for value in values]
    if length == 1:
        return 0.0
    max_lag = min(int(math.sqrt(length)), length - 1)
    gamma0 = sum(value * value for value in centered) / length
    variance = gamma0
    for lag in range(1, max_lag + 1):
        covariance = sum(centered[index] * centered[index - lag] for index in range(lag, length)) / length
        weight = 1.0 - lag / (max_lag + 1)
        variance += 2.0 * weight * covariance
    return max(variance, 0.0)


def _secondary_reports(
    candidate_series: dict[str, list[float]],
    centered_series: dict[str, list[float]],
    bootstrap_indices: list[list[int]],
    observed_candidate_statistics: dict[str, float],
    alpha: float,
    wrc_verdict: str,
    mcpm_permutation_scheme: dict | None,
    mcpm_recalculator: Callable[[dict[str, list[float]], list[int]], dict[str, list[float]]] | None,
) -> dict:
    return {
        "spa": spa_sensitivity_test(candidate_series, bootstrap_indices, alpha=alpha),
        "romano_wolf": romano_wolf_stepdown(
            candidate_series,
            centered_series,
            bootstrap_indices,
            observed_candidate_statistics,
            alpha=alpha,
            wrc_verdict=wrc_verdict,
        ),
        "mcpm": mcpm_permutation_test(
            candidate_series,
            bootstrap_indices,
            alpha=alpha,
            permutation_scheme=mcpm_permutation_scheme,
            recalculator=mcpm_recalculator,
        ),
    }


def _secondary_not_run() -> dict:
    return {
        "spa": {"status": "NOT_RUN", "role": "SECONDARY_SENSITIVITY"},
        "romano_wolf": {"status": "NOT_RUN", "role": "SECONDARY_IDENTIFICATION"},
        "mcpm": {"status": "NOT_RUN", "role": "SECONDARY_CAUSAL_PERMUTATION"},
    }


def spa_sensitivity_test(
    candidate_series: dict[str, list[float]],
    bootstrap_indices: list[list[int]],
    *,
    alpha: float,
) -> dict:
    """Hansen-style SPA sensitivity report.

    The implementation uses explicit studentization and truncates clearly bad
    observed means at zero before bootstrap recentering. The result is
    secondary and cannot open OOS when primary WRC fails.
    """
    _validate_matrix(candidate_series)
    observed = _studentized_statistics(candidate_series)
    truncated = {}
    truncated_candidate_ids = []
    active_candidate_ids = []
    for candidate_id, values in sorted(candidate_series.items()):
        mean = sum(values) / len(values)
        if mean < 0.0:
            truncated[candidate_id] = [0.0 for _ in values]
            truncated_candidate_ids.append(candidate_id)
        else:
            truncated[candidate_id] = [value - mean for value in values]
            active_candidate_ids.append(candidate_id)
    distribution = [
        max(_studentized_statistics(resample_columns(truncated, indices)).values())
        for indices in bootstrap_indices
    ]
    observed_statistic = max(observed.values())
    exceedance_count = sum(1 for statistic in distribution if statistic >= observed_statistic)
    pvalue = (1 + exceedance_count) / (len(distribution) + 1)
    return {
        "status": "EXECUTED_SECONDARY",
        "role": "SECONDARY_SENSITIVITY_TYPE_II_POWER_DIAGNOSTIC",
        "studentized_statistics": observed,
        "variance_estimator": "deterministic_hac_bartlett",
        "truncation_rule": "hansen_style_negative_mean_truncated_at_zero",
        "active_candidate_ids": active_candidate_ids,
        "truncated_candidate_ids": truncated_candidate_ids,
        "spa_pvalue": pvalue,
        "alpha": alpha,
        "sensitivity_verdict": "SUPPORTS_WRC_PASS" if pvalue < alpha else "DOES_NOT_SUPPORT_REJECTION",
        "cannot_override_wrc": True,
    }


def romano_wolf_stepdown(
    candidate_series: dict[str, list[float]],
    centered_series: dict[str, list[float]],
    bootstrap_indices: list[list[int]],
    observed_candidate_statistics: dict[str, float],
    *,
    alpha: float,
    wrc_verdict: str,
) -> dict:
    _validate_matrix(candidate_series)
    if wrc_verdict != "PASS":
        return {
            "status": "NOT_APPLICABLE_PRIMARY_WRC_NOT_PASS",
            "role": "SECONDARY_IDENTIFICATION_AFTER_GLOBAL_REJECTION",
            "cannot_override_wrc": True,
        }
    ordered = sorted(observed_candidate_statistics, key=lambda candidate_id: observed_candidate_statistics[candidate_id], reverse=True)
    remaining = list(ordered)
    rows = []
    previous_adjusted = 0.0
    for step, candidate_id in enumerate(ordered, start=1):
        observed = observed_candidate_statistics[candidate_id]
        distribution = []
        for indices in bootstrap_indices:
            resampled = resample_columns({key: centered_series[key] for key in remaining}, indices)
            distribution.append(_max_statistic(resampled))
        exceedance_count = sum(1 for statistic in distribution if statistic >= observed)
        raw_pvalue = (1 + exceedance_count) / (len(distribution) + 1)
        adjusted_pvalue = max(previous_adjusted, raw_pvalue)
        previous_adjusted = adjusted_pvalue
        decision = "REJECT" if adjusted_pvalue < alpha else "STOP_NON_REJECT"
        rows.append(
            {
                "candidate_id": candidate_id,
                "rank": step,
                "observed_statistic": observed,
                "raw_pvalue": raw_pvalue,
                "adjusted_pvalue": adjusted_pvalue,
                "decision": decision,
            }
        )
        if decision != "REJECT":
            break
        remaining.remove(candidate_id)
    return {
        "status": "EXECUTED_SECONDARY",
        "role": "SECONDARY_IDENTIFICATION_AFTER_GLOBAL_REJECTION",
        "fwer_control": "ROMANO_WOLF_STEPDOWN",
        "pvalue_monotonicity": "ENFORCED",
        "alpha": alpha,
        "candidate_results": rows,
        "cannot_override_wrc": True,
    }


def mcpm_permutation_test(
    candidate_series: dict[str, list[float]],
    bootstrap_indices: list[list[int]],
    *,
    alpha: float,
    permutation_scheme: dict | None,
    recalculator: Callable[[dict[str, list[float]], list[int]], dict[str, list[float]]] | None,
) -> dict:
    _validate_matrix(candidate_series)
    if not permutation_scheme or recalculator is None:
        return {
            "status": "BLOCKED_REQUIRES_PREREGISTERED_CAUSAL_RECALCULATION",
            "role": "SECONDARY_CAUSAL_PERMUTATION",
            "reason": "SOP 02 forbids a generic permutation of final PnL without a preregistered signal-return recalculation scheme",
            "cannot_override_wrc": True,
        }
    if not permutation_scheme.get("preserves_cross_sectional_dependence", False):
        raise ValueError("MCPM permutation scheme must preserve required cross-sectional dependence")
    distribution = []
    for indices in bootstrap_indices:
        permuted_matrix = recalculator(candidate_series, indices)
        _validate_matrix(permuted_matrix)
        distribution.append(_max_statistic(permuted_matrix))
    observed = _max_statistic(candidate_series)
    exceedance_count = sum(1 for statistic in distribution if statistic >= observed)
    pvalue = (1 + exceedance_count) / (len(distribution) + 1)
    return {
        "status": "EXECUTED_SECONDARY",
        "role": "SECONDARY_CAUSAL_PERMUTATION",
        "permutation_scheme": permutation_scheme,
        "mcpm_pvalue": pvalue,
        "alpha": alpha,
        "causal_sensitivity_verdict": "SUPPORTS_SIGNAL_RETURN_RELATION" if pvalue < alpha else "DOES_NOT_SUPPORT_SIGNAL_RETURN_RELATION",
        "cannot_override_wrc": True,
    }


def _power_diagnostics(candidate_series: dict[str, list[float]]) -> dict:
    means = {candidate_id: sum(values) / len(values) for candidate_id, values in sorted(candidate_series.items())}
    bad_candidates = [candidate_id for candidate_id, mean in means.items() if mean < 0.0]
    return {
        "status": "DIAGNOSTIC_ONLY",
        "wrc_known_power_limit": "many_bad_candidates_can_reduce_power",
        "candidate_count": len(candidate_series),
        "negative_mean_candidate_count": len(bad_candidates),
        "negative_mean_candidate_fraction": len(bad_candidates) / len(candidate_series),
        "bad_candidates_must_not_be_removed_after_observation": True,
        "non_significant_valid_wrc_is_not_inconclusive": True,
    }


def _family_catalogue_hash(candidate_series: dict[str, list[float]]) -> str:
    """SHA-256 hash of the sorted candidate_id list.

    Source: DN-008 — the WRC must cover the complete and reconstructible
    applicable family.  This hash allows auditors to verify that the family
    was frozen at the time of the WRC and that no candidate was silently
    added or removed post hoc.
    """
    payload = json.dumps(
        sorted(candidate_series.keys()),
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()
