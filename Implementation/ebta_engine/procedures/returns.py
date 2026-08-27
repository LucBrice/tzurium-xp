"""Daily return and NAV procedures.

Source: SOP 08 sections 3, 5, 6, 8, 10, 24, and 25; SOP 09B sections 3 and 33.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

import math
from typing import Any


def build_daily_return_series(observations: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for observation in observations:
        nav_open = float(observation["nav_open"])
        nav_close = float(observation["nav_close"])
        external_flow = float(observation.get("external_flow", 0.0))
        if nav_open <= 0:
            raise ValueError("nav_open must be positive for log-return calculation")
        adjusted_close = nav_close - external_flow
        if adjusted_close <= 0:
            raise ValueError("adjusted nav_close must be positive for log-return calculation")
        log_return = math.log(adjusted_close / nav_open)
        gross_pnl = float(observation.get("gross_pnl", 0.0))
        costs = float(observation.get("costs", 0.0))
        net_pnl = float(observation.get("net_pnl", gross_pnl - costs))
        rows.append(
            {
                "date": observation["date"],
                "nav_open": nav_open,
                "nav_close": nav_close,
                "external_flow": external_flow,
                "gross_pnl": gross_pnl,
                "costs": costs,
                "net_pnl": net_pnl,
                "economic_log_return": log_return,
                "economic_simple_return": math.exp(log_return) - 1.0,
                "status": observation.get("status", "EXPOSED"),
            }
        )
    return {
        "artifact_type": "daily_return_series",
        "frequency": "daily",
        "row_count": len(rows),
        "rows": rows,
    }


def mean_log_return(rows: list[dict[str, Any]], field: str = "economic_log_return") -> float:
    if not rows:
        raise ValueError("cannot compute mean on an empty series")
    return sum(float(row[field]) for row in rows) / len(rows)


def reconcile_net_pnl(row: dict[str, Any], *, tolerance: float = 1e-12) -> bool:
    expected = float(row.get("gross_pnl", 0.0)) - float(row.get("costs", 0.0))
    return abs(float(row.get("net_pnl", expected)) - expected) <= tolerance

