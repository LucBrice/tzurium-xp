"""Walk-forward fold construction helpers.

Source: SOP 04 sections 3, 9, 10, 11, 13, 17, and 22.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ebta_engine.data.local_ohlcv import OhlcvBar
from ebta_engine.procedures.walk_forward import validate_walk_forward_schedule


@dataclass(frozen=True)
class WalkForwardSplitter:
    """Build rolling Train/Test/OOS folds and validate their schedule."""

    n_folds: int
    train_size: int
    test_size: int
    oos_size: int
    purge_days: int = 0
    embargo_days: int = 0
    warmup_days: int = 0
    policy: str = "rolling"

    def __post_init__(self) -> None:
        for name in ("n_folds", "train_size", "test_size", "oos_size"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.n_folds < 2:
            raise ValueError("n_folds must be at least 2 for confirmatory walk-forward")
        for name in ("purge_days", "embargo_days", "warmup_days"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.policy.upper() not in {"ROLLING", "EXPANDING"}:
            raise ValueError("policy must be ROLLING or EXPANDING")

    def build_folds(self, bars: list[OhlcvBar]) -> list[dict[str, Any]]:
        """Return folds with bar slices and a validated SOP 04 schedule."""
        if not bars:
            raise ValueError("bars must not be empty")
        ordered = sorted(bars, key=lambda bar: bar.timestamp)
        if len({bar.asset for bar in ordered}) != 1:
            raise ValueError("WalkForwardSplitter expects bars for exactly one asset")

        gap_size = self.purge_days + self.embargo_days
        fold_stride = self.oos_size
        folds: list[dict[str, Any]] = []
        for index in range(self.n_folds):
            train_start = index * fold_stride
            if self.policy.upper() == "EXPANDING":
                train_start = 0
            train_end = train_start + self.train_size
            test_start = train_end + self.purge_days
            test_end = test_start + self.test_size
            oos_start = test_end + gap_size
            oos_end = oos_start + self.oos_size
            if oos_end > len(ordered):
                raise ValueError(
                    "not enough bars to build requested walk-forward schedule: "
                    f"need index {oos_end}, got {len(ordered)}"
                )

            train_bars = ordered[train_start:train_end]
            test_bars = ordered[test_start:test_end]
            oos_bars = ordered[oos_start:oos_end]
            self._assert_disjoint(train_bars, test_bars, oos_bars)
            folds.append(
                {
                    "fold_id": f"FOLD-{index + 1:03d}",
                    "train_bars": train_bars,
                    "test_bars": test_bars,
                    "oos_bars": oos_bars,
                    "schedule": self._schedule_row(f"FOLD-{index + 1:03d}", train_bars, test_bars, oos_bars),
                }
            )

        schedule = [fold["schedule"] for fold in folds]
        report = validate_walk_forward_schedule(
            schedule,
            information_stop_criterion={
                "criterion_type": "FIXED_FOLD_COUNT",
                "fixed_fold_count": self.n_folds,
            },
        )
        if report["status"] != "PASS":
            raise ValueError(f"invalid walk-forward schedule: {report['violations']}")
        return folds

    def schedule(self, folds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(fold["schedule"]) for fold in folds]

    def _schedule_row(
        self,
        fold_id: str,
        train_bars: list[OhlcvBar],
        test_bars: list[OhlcvBar],
        oos_bars: list[OhlcvBar],
    ) -> dict[str, Any]:
        return {
            "fold_id": fold_id,
            "train": [_day(train_bars[0]), _day(train_bars[-1])],
            "test": [_day(test_bars[0]), _day(test_bars[-1])],
            "oos": [_day(oos_bars[0]), _day(oos_bars[-1])],
            "purge_days": self.purge_days,
            "embargo_days": self.embargo_days,
            "warmup_days": self.warmup_days,
            "policy": self.policy.lower(),
            "information_cutoff": test_bars[-1].timestamp.isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def _assert_disjoint(
        train_bars: list[OhlcvBar],
        test_bars: list[OhlcvBar],
        oos_bars: list[OhlcvBar],
    ) -> None:
        train_times = {bar.timestamp for bar in train_bars}
        test_times = {bar.timestamp for bar in test_bars}
        oos_times = {bar.timestamp for bar in oos_bars}
        if train_times & test_times or train_times & oos_times:
            raise ValueError("Train bars must not overlap Test or OOS bars")
        if test_times & oos_times:
            raise ValueError("Test bars must not overlap OOS bars")


def _day(bar: OhlcvBar) -> str:
    return bar.timestamp.date().isoformat()
