"""Open composable strategy-family payload generation.

Source: PLAN_IMPLEMENTATION_MOTEUR_BACKTEST_EBTA_NAUTILUS.md Phase 1,
decisions E10, E11, and E12.
Type: CONTRACT_ENCODING.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ebta_engine.procedures._utils import canonical_json, stable_id
from ebta_engine.procedures.search_space import build_search_space_snapshot
from ebta_engine.strategy_api.payload import StrategyPayload


@dataclass(frozen=True)
class StructuralAxis:
    name: str
    values: tuple[str, ...]
    default: str
    complexity_by_value: dict[str, int]
    requires: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("axis name is required")
        if self.default not in self.values:
            raise ValueError(f"default value {self.default!r} is not in axis values")
        missing = sorted(set(self.values) - set(self.complexity_by_value))
        if missing:
            raise ValueError(f"missing complexity for axis values: {missing}")

    def allowed_values(self, selected: dict[str, str]) -> tuple[str, ...]:
        for axis_name, accepted_values in self.requires.items():
            if selected.get(axis_name) not in accepted_values:
                return (self.default,)
        return self.values

    def complexity(self, value: str) -> int:
        return self.complexity_by_value[value]


@dataclass(frozen=True)
class StrategyFamilySpec:
    strategy_family: str
    timeframe: str
    direction: str
    entry_level: str
    entry_criterion: dict[str, Any]
    exit_criterion: dict[str, Any]
    risk_model: str
    sizing_model: str
    parameters: dict[str, Any]
    axes: tuple[StructuralAxis, ...]
    payload_code_prefix: str = "AUTO"
    payload_version: str = "1.1.0"

    def __post_init__(self) -> None:
        axis_names = [axis.name for axis in self.axes]
        if len(axis_names) != len(set(axis_names)):
            raise ValueError("axis names must be unique")


def generate_family(
    *,
    assets: list[str],
    spec: StrategyFamilySpec,
    research_family_id: str,
    fold_id: str,
) -> dict[str, Any]:
    if not assets:
        raise ValueError("assets must not be empty")
    combinations = _axis_combinations(spec.axes)
    payloads: list[StrategyPayload] = []
    parameter_rows: list[dict[str, Any]] = []
    for asset in sorted(assets):
        for index, selected in enumerate(combinations, start=1):
            complexity = sum(axis.complexity(selected[axis.name]) for axis in spec.axes)
            payload_code = f"{spec.payload_code_prefix}-{asset}-{index:02d}"
            payload = StrategyPayload(
                asset=asset,
                timeframe=spec.timeframe,
                strategy_family=spec.strategy_family,
                payload_code=payload_code,
                direction=spec.direction,
                entry_level=spec.entry_level,
                entry_criterion=spec.entry_criterion,
                bias_filter=selected.get("bias_filter", "none"),
                time_filter="session_window" if selected.get("session", "all") != "all" else "none",
                session=selected.get("session", "all"),
                exit_criterion=spec.exit_criterion,
                risk_model=spec.risk_model,
                sizing_model=spec.sizing_model,
                parameters={**spec.parameters, **selected, "complexity": complexity},
                payload_version=spec.payload_version,
            )
            payloads.append(payload)
            parameter_rows.append(
                {
                    "asset": asset,
                    "payload_code": payload_code,
                    "complexity": complexity,
                    **selected,
                }
            )
    search_space = _search_space_from_rows(
        research_family_id=research_family_id,
        fold_id=fold_id,
        rows=parameter_rows,
        assets=sorted(assets),
        base_spec={"strategy_family": spec.strategy_family},
    )
    return {"payloads": payloads, "search_space": search_space}


def _axis_combinations(axes: tuple[StructuralAxis, ...]) -> list[dict[str, str]]:
    combinations: list[dict[str, str]] = [{}]
    for axis in axes:
        next_combinations: list[dict[str, str]] = []
        for selected in combinations:
            for value in axis.allowed_values(selected):
                next_combinations.append({**selected, axis.name: value})
        combinations = next_combinations
    return combinations


def _search_space_from_rows(
    *,
    research_family_id: str,
    fold_id: str,
    rows: list[dict[str, Any]],
    assets: list[str],
    base_spec: dict[str, Any],
) -> dict[str, Any]:
    parameters = {key: sorted({row[key] for row in rows}) for key in rows[0]}
    snapshot = build_search_space_snapshot(
        research_family_id,
        fold_id,
        parameters,
        base_spec=base_spec,
        asset_universe=assets,
        asset_selection_axis="asset",
        asset_selection_rule="evaluate_all_declared_assets",
    )
    row_keys = sorted(rows[0])
    allowed = {tuple((key, row[key]) for key in row_keys) for row in rows}
    snapshot["candidates"] = [
        candidate
        for candidate in snapshot["candidates"]
        if tuple((key, candidate["parameters"][key]) for key in row_keys) in allowed
    ]
    snapshot["candidate_count"] = len(snapshot["candidates"])
    snapshot["asset_candidate_count"] = {
        asset: sum(1 for candidate in snapshot["candidates"] if candidate.get("asset") == asset)
        for asset in assets
    }
    snapshot["candidate_asset_map"] = {
        candidate["candidate_id"]: candidate["asset"]
        for candidate in snapshot["candidates"]
    }
    canonical_specs = [candidate["canonical_spec"] for candidate in snapshot["candidates"]]
    snapshot["canonical_hash"] = stable_id("SPACE", canonical_specs, 16)
    snapshot["canonical_json"] = canonical_json(canonical_specs)
    return snapshot
