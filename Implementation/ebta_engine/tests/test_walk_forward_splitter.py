import unittest
from datetime import datetime, timedelta, timezone

from ebta_engine.data.local_ohlcv import OhlcvBar
from ebta_engine.data.walk_forward import WalkForwardSplitter
from ebta_engine.procedures.walk_forward import validate_walk_forward_schedule


class WalkForwardSplitterTests(unittest.TestCase):
    def test_builds_valid_multifold_schedule_without_train_leakage(self):
        bars = _daily_bars(10)
        splitter = WalkForwardSplitter(
            n_folds=2,
            train_size=2,
            test_size=1,
            oos_size=1,
            purge_days=1,
            embargo_days=0,
            warmup_days=1,
        )
        folds = splitter.build_folds(bars)
        schedule = splitter.schedule(folds)
        report = validate_walk_forward_schedule(schedule)

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(folds), 2)
        for fold in folds:
            train_times = {bar.timestamp for bar in fold["train_bars"]}
            test_times = {bar.timestamp for bar in fold["test_bars"]}
            oos_times = {bar.timestamp for bar in fold["oos_bars"]}
            self.assertFalse(train_times & test_times)
            self.assertFalse(train_times & oos_times)
        self.assertIn("purge_days", schedule[0])
        self.assertIn("embargo_days", schedule[0])
        self.assertIn("warmup_days", schedule[0])

    def test_requires_at_least_two_folds(self):
        with self.assertRaises(ValueError):
            WalkForwardSplitter(n_folds=1, train_size=2, test_size=1, oos_size=1)


def _daily_bars(count: int) -> list[OhlcvBar]:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    return [
        OhlcvBar(
            asset="NASDAQ",
            timestamp=start + timedelta(days=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
            volume=1.0,
        )
        for index in range(count)
    ]


if __name__ == "__main__":
    unittest.main()
