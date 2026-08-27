import unittest
import csv
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ebta_engine.data.local_ohlcv import DEFAULT_DATA_ROOT, build_data_snapshot, inspect_ohlcv_window, resolve_data_root


class DataRootResolutionTests(unittest.TestCase):
    def test_explicit_path_has_priority_over_environment(self):
        explicit = Path("explicit-data")
        resolved = resolve_data_root(explicit, environ={"EBTA_DATA_ROOT": "environment-data"})
        self.assertEqual(resolved, explicit)

    def test_environment_path_is_used_when_argument_is_absent(self):
        resolved = resolve_data_root(None, environ={"EBTA_DATA_ROOT": "environment-data"})
        self.assertEqual(resolved, Path("environment-data"))

    def test_legacy_default_is_used_when_no_override_exists(self):
        resolved = resolve_data_root(None, environ={})
        self.assertEqual(resolved, DEFAULT_DATA_ROOT)


class OhlcvWindowInspectionTests(unittest.TestCase):
    def test_snapshot_counts_more_than_ten_thousand_bars_exactly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            row_count = 10_001
            _write_rows(root, [_valid_row(index) for index in range(row_count)])
            report = inspect_ohlcv_window(
                root,
                "NASDAQ",
                start="2020-01-01T00:00:00Z",
                end="2020-01-07T22:40:00Z",
            )
            snapshot = build_data_snapshot(
                root,
                ["NASDAQ"],
                start="2020-01-01T00:00:00Z",
                end="2020-01-07T22:40:00Z",
            )

        self.assertEqual(report["bar_count"], row_count)
        self.assertEqual(snapshot["assets"][0]["loaded_bar_count"], row_count)
        self.assertEqual(snapshot["assets"][0]["content_checksum"], report["content_checksum"])
        self.assertEqual(len(snapshot["content_checksum"]), 64)
        self.assertEqual(len(snapshot["checksum"]), 64)

    def test_time_gaps_are_reported_without_becoming_a_quality_failure(self):
        rows = [_valid_row(0), _valid_row(2), _valid_row(62)]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_rows(root, rows)
            report = inspect_ohlcv_window(
                root,
                "NASDAQ",
                start="2020-01-01T00:00:00Z",
                end="2020-01-01T01:02:00Z",
            )

        self.assertEqual(report["gap_count"], 2)
        self.assertEqual(report["maximum_gap_seconds"], 3600.0)
        self.assertEqual(report["gap_policy"], "descriptive_only_no_normative_venue_calendar")

    def test_invalid_rows_fail_with_context(self):
        cases = {
            "naive timestamp": {**_valid_row(0), "timestamp": "2020-01-01T00:00:00"},
            "duplicate timestamp": None,
            "non-finite OHLCV": {**_valid_row(0), "open": "nan"},
            "inconsistent OHLC envelope": {**_valid_row(0), "high": "99"},
            "negative volume": {**_valid_row(0), "volume": "-1"},
        }
        for label, invalid_row in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                rows = [_valid_row(0), _valid_row(1)]
                if invalid_row is None:
                    rows[1] = dict(rows[0])
                else:
                    rows[0] = invalid_row
                _write_rows(root, rows)
                with self.assertRaises(ValueError):
                    inspect_ohlcv_window(
                        root,
                        "NASDAQ",
                        start="2020-01-01T00:00:00Z",
                        end="2020-01-01T00:01:00Z",
                    )

    def test_non_monotonic_rows_and_wrong_header_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_rows(root, [_valid_row(1), _valid_row(0)])
            with self.assertRaisesRegex(ValueError, "non-monotonic"):
                inspect_ohlcv_window(
                    root,
                    "NASDAQ",
                    start="2020-01-01T00:00:00Z",
                    end="2020-01-01T00:01:00Z",
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = root / "NASDAQ 1m"
            folder.mkdir(parents=True)
            (folder / "bad.csv").write_text("timestamp,open\n2020-01-01T00:00:00Z,100\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "header"):
                inspect_ohlcv_window(
                    root,
                    "NASDAQ",
                    start="2020-01-01T00:00:00Z",
                    end="2020-01-01T00:01:00Z",
                )


def _valid_row(minute: int) -> dict[str, str]:
    timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    return {
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "open": "100",
        "high": "102",
        "low": "99",
        "close": "101",
        "volume": "10",
    }


def _write_rows(data_root: Path, rows: list[dict[str, str]]) -> None:
    folder = data_root / "NASDAQ 1m"
    folder.mkdir(parents=True)
    with (folder / "NASDAQ.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)

    def test_blank_environment_value_falls_back_to_legacy_default(self):
        resolved = resolve_data_root(None, environ={"EBTA_DATA_ROOT": "  "})
        self.assertEqual(resolved, DEFAULT_DATA_ROOT)


if __name__ == "__main__":
    unittest.main()
