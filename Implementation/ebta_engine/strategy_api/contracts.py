"""Open stdlib-only contracts shared by EBTA strategy and adapter layers.

Source: PLAN_IMPLEMENTATION_MOTEUR_BACKTEST_EBTA_NAUTILUS.md Phase 1.
Type: CONTRACT_ENCODING.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    research_family_id: str
    payload: dict[str, Any]
    asset: str
    complexity: int
    fold_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id is required")
        if not self.research_family_id:
            raise ValueError("research_family_id is required")
        if not self.asset:
            raise ValueError("asset is required")
        if self.complexity < 0:
            raise ValueError("complexity must be non-negative")

    @property
    def canonical_hash(self) -> str:
        return _canonical_hash(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if include_hash:
            payload["canonical_hash"] = self.canonical_hash
        return payload


@dataclass(frozen=True)
class CostModel:
    model_id: str
    fill_model: str
    fee_model: str
    commission_per_lot: float = 0.0
    slippage_bps: float = 0.0
    spread_points: float = 0.0
    point_value: float = 1.0
    financing_rate_daily: float = 0.0
    impact_model: str = "none"
    latency_nanos: int = 0
    prob_fill_on_limit: float = 1.0
    prob_slippage: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model_id is required")
        if not self.fill_model:
            raise ValueError("fill_model is required")
        if not self.fee_model:
            raise ValueError("fee_model is required")
        if self.latency_nanos < 0:
            raise ValueError("latency_nanos must be non-negative")
        for name, value in {
            "commission_per_lot": self.commission_per_lot,
            "slippage_bps": self.slippage_bps,
            "spread_points": self.spread_points,
            "point_value": self.point_value,
            "financing_rate_daily": self.financing_rate_daily,
        }.items():
            if value < 0.0:
                raise ValueError(f"{name} must be non-negative")
        for name, value in {
            "prob_fill_on_limit": self.prob_fill_on_limit,
            "prob_slippage": self.prob_slippage,
        }.items():
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InstrumentConfig:
    instrument_id: str
    symbol: str
    venue: str
    price_precision: int
    size_precision: int
    price_increment: str
    size_increment: str
    margin_init: str
    margin_maint: str
    maker_fee: str
    taker_fee: str
    base_currency: str = "USD"
    quote_currency: str = "USD"
    asset_class: str = "CFD"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ["instrument_id", "symbol", "venue", "price_increment", "size_increment"]:
            if not getattr(self, name):
                raise ValueError(f"{name} is required")
        if self.price_precision < 0 or self.size_precision < 0:
            raise ValueError("precision fields must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulationResult:
    candidate_id: str
    instrument_id: str
    timestamps: list[str]
    daily_returns: list[float]
    daily_exposure: list[float]
    nav: list[float]
    total_costs: float
    orders: list[dict[str, Any]] = field(default_factory=list)
    fills: list[dict[str, Any]] = field(default_factory=list)
    positions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        lengths = {len(self.timestamps), len(self.daily_returns), len(self.daily_exposure), len(self.nav)}
        if len(lengths) != 1:
            raise ValueError("timestamps, daily_returns, daily_exposure, and nav must share the same length")
        if not self.timestamps:
            raise ValueError("simulation result series must not be empty")
        if self.total_costs < 0:
            raise ValueError("total_costs must be non-negative")

    @property
    def result_hash(self) -> str:
        return _canonical_hash(self.to_dict(include_hash=False))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        if include_hash:
            payload["result_hash"] = self.result_hash
        return payload

    def detrending_inputs(
        self,
        *,
        market_returns: list[float],
        cash_returns: list[float],
    ) -> dict[str, list[float]]:
        return {
            "strat_net_returns": list(self.daily_returns),
            "market_returns": list(market_returns),
            "cash_returns": list(cash_returns),
            "exposures": list(self.daily_exposure),
        }

    def economic_gate_evidence(
        self,
        *,
        statistical_status: str,
        thresholds: dict[str, Any],
        observed_values: dict[str, Any],
        capacity_grid: list[dict[str, Any]],
        return_hurdle_pass: bool,
        drawdown_pass: bool,
        capacity_pass: bool,
        costs_pass: bool,
        execution_pass: bool,
    ) -> dict[str, Any]:
        return {
            "statistical_status": statistical_status,
            "thresholds": dict(thresholds),
            "observed_values": dict(observed_values),
            "capacity_grid": list(capacity_grid),
            "return_hurdle_pass": return_hurdle_pass,
            "drawdown_pass": drawdown_pass,
            "capacity_pass": capacity_pass,
            "costs_pass": costs_pass,
            "execution_pass": execution_pass,
            "simulation_result_hash": self.result_hash,
            "total_costs": self.total_costs,
        }


@runtime_checkable
class SegmentSimulator(Protocol):
    """Adapter boundary contract for one opaque EBTA segment simulation."""

    def run(self, candidate: Candidate) -> SimulationResult:
        """Run one candidate without exposing Train/Test/OOS identity."""
        ...
