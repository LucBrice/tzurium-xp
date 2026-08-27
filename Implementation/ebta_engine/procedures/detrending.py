"""Detrending procedures for the EBTA evaluation flow.

Source: SOP 07 sections 3, 6, 8, 14, 20, and 26; SOP 08 section 6.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any


def detrend_returns(
    strat_net_returns: list[float],
    market_returns: list[float],
    cash_returns: list[float],
    exposures: list[float],
    *,
    segment_id: str,
) -> dict[str, Any]:
    lengths = {len(strat_net_returns), len(market_returns), len(cash_returns), len(exposures)}
    if len(lengths) != 1:
        raise ValueError("strat, market, cash, and exposure series must share the same length")
    if not strat_net_returns:
        raise ValueError("cannot detrend an empty series")
    market_drift = sum(market_returns) / len(market_returns)
    cash_drift = sum(cash_returns) / len(cash_returns)
    detrended = [
        float(strat) - float(cash) - float(exposure) * (market_drift - cash_drift)
        for strat, cash, exposure in zip(strat_net_returns, cash_returns, exposures, strict=True)
    ]
    return {
        "artifact_type": "detrending_report",
        "segment_id": segment_id,
        "formula_version": "SOP07_SECTION_6_SINGLE_ASSET",
        "market_drift": market_drift,
        "cash_drift": cash_drift,
        "detrended_returns": detrended,
    }


def fit_train_only_transformation(name: str, values: list[float], *, fit_segment: str) -> dict[str, Any]:
    if fit_segment != "Train_k":
        raise ValueError("learned transformations must be fit exclusively on Train_k")
    if not values:
        raise ValueError("cannot fit a transformation on an empty series")
    return {
        "name": name,
        "fit_segment": fit_segment,
        "mean": sum(values) / len(values),
        "count": len(values),
    }


def assert_signal_flow_unchanged(before: list[Any], after: list[Any]) -> bool:
    return before == after
