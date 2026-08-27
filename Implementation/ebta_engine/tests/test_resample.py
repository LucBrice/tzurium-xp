import unittest
from datetime import datetime, timezone

from ebta_engine.data.local_ohlcv import OhlcvBar
from ebta_engine.data.resample import resample_ohlcv


class ResampleOhlcvTests(unittest.TestCase):
    def test_hourly_timestamps_align_to_close_boundaries(self):
        bars = [
            _bar("2026-01-01T08:59:00Z", 100.0, volume=1.0),
            _bar("2026-01-01T09:00:00Z", 101.0, volume=2.0),
            _bar("2026-01-01T09:01:00Z", 102.0, volume=3.0),
        ]

        actual = resample_ohlcv(bars, 60)

        self.assertEqual(
            [bar.timestamp.isoformat().replace("+00:00", "Z") for bar in actual],
            ["2026-01-01T09:00:00Z", "2026-01-01T10:00:00Z"],
        )

    def test_volume_is_conserved(self):
        bars = [
            _bar("2026-01-01T08:58:00Z", 100.0, volume=1.5),
            _bar("2026-01-01T08:59:00Z", 101.0, volume=2.5),
            _bar("2026-01-01T09:00:00Z", 102.0, volume=3.5),
        ]

        actual = resample_ohlcv(bars, 60)

        self.assertEqual(len(actual), 1)
        self.assertAlmostEqual(actual[0].volume, 7.5)

    def test_output_is_monotonic_even_if_input_is_unsorted(self):
        bars = [
            _bar("2026-01-01T09:01:00Z", 102.0, volume=3.0),
            _bar("2026-01-01T08:59:00Z", 100.0, volume=1.0),
            _bar("2026-01-01T09:00:00Z", 101.0, volume=2.0),
        ]

        actual = resample_ohlcv(bars, 60)

        self.assertLess(actual[0].timestamp, actual[1].timestamp)

    def test_upper_boundary_is_included_not_carried_forward(self):
        bars = [
            _bar("2026-01-01T08:59:00Z", 100.0, volume=1.0),
            _bar("2026-01-01T09:00:00Z", 101.0, volume=2.0),
            _bar("2026-01-01T09:01:00Z", 200.0, volume=3.0),
        ]

        actual = resample_ohlcv(bars, 60)

        self.assertEqual(actual[0].timestamp, _dt("2026-01-01T09:00:00Z"))
        self.assertEqual(actual[0].close, 101.0)
        self.assertEqual(actual[1].open, 200.0)


def _bar(timestamp: str, price: float, *, volume: float) -> OhlcvBar:
    return OhlcvBar(
        asset="XAUUSD",
        timestamp=_dt(timestamp),
        open=price,
        high=price + 1.0,
        low=price - 1.0,
        close=price,
        volume=volume,
    )


def _dt(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc)


if __name__ == "__main__":
    unittest.main()
