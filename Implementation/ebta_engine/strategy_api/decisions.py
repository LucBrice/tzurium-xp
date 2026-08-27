"""Open decision-provider boundary between private strategies and adapters."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ebta_engine.data.local_ohlcv import OhlcvBar
from ebta_engine.strategy_api.payload import StrategyPayload


Decision = tuple[int, str]


class DecisionProvider(Protocol):
    def __call__(
        self,
        payload: StrategyPayload,
        bars: Sequence[OhlcvBar],
        *,
        warmup_bar_count: int,
    ) -> list[Decision]: ...
