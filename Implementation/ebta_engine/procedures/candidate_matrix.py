"""Candidate matrix construction for complete Test-side families.

Source: SOP 03 section 14; SOP 02 sections 4 and 5; SOP 06 section 17.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any

from ebta_engine.procedures._utils import stable_id


def build_candidate_matrix(
    candidate_series: dict[str, list[float]],
    *,
    dates: list[str] | None = None,
    influential_candidates: list[str] | None = None,
    asset_universe: list[str] | None = None,
    candidate_assets: dict[str, str] | None = None,
    fold_id: str = "FOLD-001",
) -> dict[str, Any]:
    if not candidate_series:
        raise ValueError("candidate matrix requires at least one candidate")
    columns = sorted(candidate_series)
    lengths = {len(candidate_series[candidate_id]) for candidate_id in columns}
    if len(lengths) != 1:
        raise ValueError("all candidate series must share the same length")
    row_count = lengths.pop()
    if dates is None:
        dates = [str(index) for index in range(row_count)]
    if len(dates) != row_count:
        raise ValueError("dates length must match candidate series length")

    influential = set(influential_candidates or columns)
    missing = sorted(influential.difference(columns))
    if missing:
        raise ValueError(f"influential candidates missing from matrix: {missing}")

    active_asset_axis = asset_universe is not None or candidate_assets is not None
    if active_asset_axis:
        if not asset_universe:
            raise ValueError("asset_universe is required when candidate assets are provided")
        if not candidate_assets:
            raise ValueError("candidate_assets is required when asset_universe is provided")
        undeclared_candidates = sorted(set(candidate_assets) - set(columns))
        if undeclared_candidates:
            raise ValueError(f"candidate asset map references candidates outside matrix: {undeclared_candidates}")
        unmapped_candidates = sorted(set(columns) - set(candidate_assets))
        if unmapped_candidates:
            raise ValueError(f"matrix candidates missing asset mapping: {unmapped_candidates}")
        universe = set(asset_universe)
        unknown_assets = sorted(set(candidate_assets.values()) - universe)
        if unknown_assets:
            raise ValueError(f"candidate asset map contains assets outside asset_universe: {unknown_assets}")
        uncovered_assets = sorted(universe - set(candidate_assets.values()))
        if uncovered_assets:
            raise ValueError(f"asset_universe assets missing from matrix candidates: {uncovered_assets}")

    rows = []
    for row_index, date in enumerate(dates):
        rows.append({"date": date, "values": {candidate_id: candidate_series[candidate_id][row_index] for candidate_id in columns}})

    payload: dict[str, Any] = {
        "artifact_type": "candidate_matrix",
        "fold_id": fold_id,
        "candidate_ids": columns,
        "row_count": row_count,
        "rows": rows,
        "complete_family": True,
    }
    if active_asset_axis:
        assert asset_universe is not None and candidate_assets is not None
        payload["asset_universe"] = sorted(asset_universe)
        payload["candidate_assets"] = {candidate_id: candidate_assets[candidate_id] for candidate_id in columns}
    payload["matrix_id"] = stable_id("MATRIX", payload, 16)
    return payload
