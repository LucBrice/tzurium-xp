"""Open serializable strategy payload contract.

Source: PLAN_IMPLEMENTATION_MOTEUR_BACKTEST_EBTA_NATIF.md Phase 3 and
read-only BACKTRADER audit of strategies/sweep_lq.py.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass(frozen=True)
class StrategyPayload:
    asset: str
    timeframe: str
    strategy_family: str
    payload_code: str
    direction: str
    entry_level: str
    entry_criterion: str | dict[str, Any]
    bias_filter: str
    time_filter: str
    session: str
    exit_criterion: str | dict[str, Any]
    risk_model: str
    sizing_model: str
    parameters: dict
    payload_version: str = "1.0.0"

    @property
    def payload_hash(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["payload_hash"] = self.payload_hash
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategyPayload":
        payload = dict(payload)
        supplied_hash = payload.pop("payload_hash", None)
        allowed = {field.name for field in fields(cls)}
        unexpected = sorted(set(payload) - allowed)
        if unexpected:
            raise ValueError(f"unexpected StrategyPayload fields: {unexpected}")
        missing = sorted(name for name in allowed if name not in payload and name != "payload_version")
        if missing:
            raise ValueError(f"missing StrategyPayload fields: {missing}")
        result = cls(**payload)
        if supplied_hash is not None and supplied_hash != result.payload_hash:
            raise ValueError("payload_hash does not match StrategyPayload content")
        return result
