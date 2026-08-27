import json
import tempfile
import unittest
from pathlib import Path

from ebta_engine.package_builder.execution_calibration import (
    broker_series_summary,
    build_execution_calibration,
    quantile_from_frequencies,
    write_calibration,
)


class ExecutionCalibrationTests(unittest.TestCase):
    def test_frequency_quantiles_use_linear_interpolation(self):
        frequencies = {1000: 1, 2000: 2, 4000: 1}
        self.assertEqual(quantile_from_frequencies(frequencies, 0.5), 2.0)
        self.assertAlmostEqual(quantile_from_frequencies(frequencies, 0.75), 2.5)

    def test_broker_summary_keeps_constituents_and_small_n(self):
        summary = broker_series_summary(
            {
                "unit": "point",
                "observations": [
                    {"value": 1.0, "statistic_kind": "minimum"},
                    {"value": 3.0, "statistic_kind": "average"},
                ],
            }
        )
        self.assertEqual(summary["constituents"], [1.0, 3.0])
        self.assertEqual(summary["sample_size"], 2)
        self.assertEqual(summary["arithmetic_mean"], 2.0)
        self.assertEqual(summary["classification"], "BROKER_PROXY")

    def test_build_scans_ticks_and_writes_deterministic_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tick_root = root / "NASDAQ tick"
            tick_root.mkdir()
            for month in range(1, 37):
                year = 2023 + (month - 1) // 12
                calendar_month = (month - 1) % 12 + 1
                path = tick_root / f"USATECH.IDXUSD-tick-bid-{year}-{calendar_month:02d}-01.csv"
                path.write_text(
                    "timestamp,ask,bid,ask_volume,bid_volume\n"
                    "2023-01-01T00:00:00Z,102.000,100.000,1,1\n"
                    "2023-01-01T00:00:01Z,104.000,100.000,1,1\n",
                    encoding="utf-8",
                )
            source = root / "broker_sources.json"
            source.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0.0",
                        "retrieved_at": "2026-07-21",
                        "series": {
                            "NASDAQ_SPREAD_POINTS": _series("NASDAQ", "spread", "point", [1.0, 2.0]),
                            "XAUUSD_SPREAD_POINTS": _series("XAUUSD", "spread", "point", [0.1, 0.3]),
                            "BROKER_EXECUTION_LATENCY_MS": _series("CROSS_ASSET", "latency", "millisecond", [10.0, 30.0]),
                            "INDEX_ADVERSE_SLIPPAGE_PROBABILITY": _series("NASDAQ", "prob_slippage", "probability", [0.25]),
                            "STANDARD_CFD_COMMISSION_RATE": _series("CROSS_ASSET", "commission_rate", "notional_fraction", [0.0]),
                        },
                    }
                ),
                encoding="utf-8",
            )
            payload = build_execution_calibration(root, source_path=source)
            self.assertEqual(payload["nasdaq_local"]["file_count"], 36)
            self.assertEqual(payload["nasdaq_local"]["valid_rows"], 72)
            self.assertEqual(payload["nasdaq_local"]["quantiles"]["CENTRAL"], 3.0)
            self.assertNotIn(str(root), json.dumps(payload))
            output = root / "output"
            write_calibration(payload, output)
            first = (output / "calibration.json").read_bytes()
            write_calibration(payload, output)
            self.assertEqual((output / "calibration.json").read_bytes(), first)


def _series(asset, component, unit, values):
    return {
        "asset": asset,
        "component": component,
        "unit": unit,
        "observations": [
            {
                "broker": f"B{index}",
                "value": value,
                "statistic_kind": "test",
                "url": f"https://example.test/{index}",
                "limit": "fixture",
            }
            for index, value in enumerate(values)
        ],
    }


if __name__ == "__main__":
    unittest.main()
