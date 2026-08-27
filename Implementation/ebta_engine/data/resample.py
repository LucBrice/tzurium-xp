"""Causal OHLCV resampling helpers for EBTA bars.

Source: PLAN_R1_R2_SIGNAUX_ET_EXTRACTION_NAUTILUS.md Phase 0.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ebta_engine.data.local_ohlcv import OhlcvBar


def resample_ohlcv(bars: list[OhlcvBar], target_minutes: int) -> list[OhlcvBar]:
    """Resample M1 bars into right-closed target-minute OHLCV bars.

    Each output bar ending at ``t_close`` contains source bars satisfying
    ``t_open < timestamp <= t_close``. No output bar can include a source bar
    with a timestamp later than its own timestamp.
    """
    if target_minutes <= 0:
        raise ValueError("target_minutes must be positive")
    if not bars:
        return []

    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    assets = {bar.asset for bar in ordered}
    if len(assets) != 1:
        raise ValueError(f"bars must contain exactly one asset, got {sorted(assets)}")

    period_seconds = target_minutes * 60
    buckets: dict[datetime, list[OhlcvBar]] = {}
    for bar in ordered:
        timestamp = _as_utc(bar.timestamp)
        close_time = _right_closed_boundary(timestamp, period_seconds)
        buckets.setdefault(close_time, []).append(bar)

    asset = ordered[0].asset
    resampled: list[OhlcvBar] = []
    for close_time in sorted(buckets):
        bucket = buckets[close_time]
        resampled.append(
            OhlcvBar(
                asset=asset,
                timestamp=close_time,
                open=float(bucket[0].open),
                high=max(float(bar.high) for bar in bucket),
                low=min(float(bar.low) for bar in bucket),
                close=float(bucket[-1].close),
                volume=sum(float(bar.volume) for bar in bucket),
            )
        )
    return resampled


def _right_closed_boundary(timestamp: datetime, period_seconds: int) -> datetime:
    seconds = int(timestamp.timestamp())
    boundary = ((seconds + period_seconds - 1) // period_seconds) * period_seconds
    return datetime.fromtimestamp(boundary, timezone.utc)


def _as_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        raise ValueError(f"timestamp is not timezone-aware: {timestamp!r}")
    return timestamp.astimezone(timezone.utc)
