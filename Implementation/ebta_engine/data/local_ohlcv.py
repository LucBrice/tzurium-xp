"""Local OHLCV CSV loader for the native EBTA MVP.

Source: PLAN_IMPLEMENTATION_MOTEUR_BACKTEST_EBTA_NATIF.md Phase 2.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

import csv
import hashlib
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping


DEFAULT_DATA_ROOT = Path(r"D:\TRADING\ENTREPRISE\0 - Phase de lancement\Stratégie de trading\0 - Backtest\Data")
DEFAULT_ASSET_DIRECTORIES = {
    "XAUUSD": "XAUUSD 1m",
    "NASDAQ": "NASDAQ 1m",
}
REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def resolve_data_root(
    data_root: Path | str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the OHLCV root once at the build boundary.

    An explicit caller value takes priority over ``EBTA_DATA_ROOT``. The
    historical local path remains the final compatibility fallback.
    """

    if data_root is not None:
        return Path(data_root)
    environment = os.environ if environ is None else environ
    configured_root = environment.get("EBTA_DATA_ROOT", "").strip()
    return Path(configured_root) if configured_root else DEFAULT_DATA_ROOT


@dataclass(frozen=True)
class OhlcvBar:
    asset: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp is not timezone-aware: {value}")
    return parsed.astimezone(timezone.utc)


def list_asset_files(data_root: Path, asset: str) -> list[Path]:
    folder_name = DEFAULT_ASSET_DIRECTORIES.get(asset)
    if folder_name is None:
        raise ValueError(f"unsupported MVP asset: {asset}")
    folder = data_root / folder_name
    if not folder.exists():
        raise FileNotFoundError(f"asset data folder not found: {folder}")
    files = sorted(folder.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"no CSV files found for asset {asset}: {folder}")
    return files


def load_ohlcv_bars(
    data_root: Path,
    asset: str,
    *,
    start: str | None = None,
    end: str | None = None,
    max_bars: int | None = None,
) -> list[OhlcvBar]:
    start_ts = parse_utc_timestamp(start) if start else None
    end_ts = parse_utc_timestamp(end) if end else None
    bars: list[OhlcvBar] = []
    for csv_path in list_asset_files(data_root, asset):
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or any(column not in reader.fieldnames for column in REQUIRED_COLUMNS):
                raise ValueError(f"CSV missing OHLCV columns: {csv_path}")
            for row in reader:
                timestamp = parse_utc_timestamp(row["timestamp"])
                if start_ts and timestamp < start_ts:
                    continue
                if end_ts and timestamp > end_ts:
                    return bars
                bars.append(
                    OhlcvBar(
                        asset=asset,
                        timestamp=timestamp,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"]),
                    )
                )
                if max_bars is not None and len(bars) >= max_bars:
                    return bars
    return bars


def inspect_ohlcv_window(
    data_root: Path,
    asset: str,
    *,
    start: str,
    end: str,
) -> dict:
    """Validate and fingerprint one UTC OHLCV window without retaining bars.

    Time gaps are descriptive only: EBTA does not own a venue calendar from
    which a missing-market-data verdict could be derived.
    """

    start_ts = parse_utc_timestamp(start)
    end_ts = parse_utc_timestamp(end)
    if end_ts < start_ts:
        raise ValueError("end must not precede start")

    content_checksum = hashlib.sha256()
    selected_files: list[str] = []
    previous_timestamp: datetime | None = None
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    row_count = 0
    gap_count = 0
    maximum_gap_seconds = 0.0
    gap_buckets = {
        "over_1_minute_to_1_hour": 0,
        "over_1_hour_to_1_day": 0,
        "over_1_day": 0,
    }

    for csv_path in list_asset_files(data_root, asset):
        file_selected = False
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
                raise ValueError(f"CSV header must equal {REQUIRED_COLUMNS}: {csv_path}")
            for line_number, row in enumerate(reader, start=2):
                try:
                    timestamp = parse_utc_timestamp(row["timestamp"])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid timestamp at {csv_path}:{line_number}: {exc}") from exc
                if timestamp < start_ts:
                    continue
                if timestamp > end_ts:
                    break

                values = _validated_ohlcv_values(row, csv_path, line_number)
                if previous_timestamp is not None:
                    if timestamp == previous_timestamp:
                        raise ValueError(f"duplicate timestamp at {csv_path}:{line_number}: {row['timestamp']}")
                    if timestamp < previous_timestamp:
                        raise ValueError(f"non-monotonic timestamp at {csv_path}:{line_number}: {row['timestamp']}")
                    gap_seconds = (timestamp - previous_timestamp).total_seconds()
                    if gap_seconds > 60.0:
                        gap_count += 1
                        maximum_gap_seconds = max(maximum_gap_seconds, gap_seconds)
                        if gap_seconds <= 3600.0:
                            gap_buckets["over_1_minute_to_1_hour"] += 1
                        elif gap_seconds <= 86400.0:
                            gap_buckets["over_1_hour_to_1_day"] += 1
                        else:
                            gap_buckets["over_1_day"] += 1

                if not file_selected:
                    selected_files.append(csv_path.name)
                    file_selected = True
                previous_timestamp = timestamp
                first_timestamp = first_timestamp or timestamp
                last_timestamp = timestamp
                row_count += 1
                canonical_row = [timestamp.isoformat().replace("+00:00", "Z"), *(format(value, ".17g") for value in values)]
                content_checksum.update(("\x1f".join(canonical_row) + "\n").encode("utf-8"))

    if row_count == 0 or first_timestamp is None or last_timestamp is None:
        raise ValueError(f"no bars loaded for {asset} in requested window {start}..{end}")

    return {
        "asset": asset,
        "requested_start": start_ts.isoformat().replace("+00:00", "Z"),
        "requested_end": end_ts.isoformat().replace("+00:00", "Z"),
        "observed_start": first_timestamp.isoformat().replace("+00:00", "Z"),
        "observed_end": last_timestamp.isoformat().replace("+00:00", "Z"),
        "bar_count": row_count,
        "selected_file_count": len(selected_files),
        "selected_files": selected_files,
        "content_checksum": content_checksum.hexdigest(),
        "gap_count": gap_count,
        "maximum_gap_seconds": maximum_gap_seconds,
        "gap_buckets": gap_buckets,
        "gap_policy": "descriptive_only_no_normative_venue_calendar",
    }


def _validated_ohlcv_values(row: Mapping[str, str], csv_path: Path, line_number: int) -> tuple[float, ...]:
    try:
        values = tuple(float(row[column]) for column in ("open", "high", "low", "close", "volume"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric OHLCV value at {csv_path}:{line_number}") from exc
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"non-finite OHLCV value at {csv_path}:{line_number}")
    open_price, high, low, close, volume = values
    if high < max(open_price, low, close) or low > min(open_price, high, close):
        raise ValueError(f"inconsistent OHLC envelope at {csv_path}:{line_number}")
    if volume < 0.0:
        raise ValueError(f"negative volume at {csv_path}:{line_number}")
    return values


def build_data_snapshot(
    data_root: Path,
    assets: Iterable[str],
    *,
    start: str,
    end: str,
    snapshot_id: str = "DATA-NATIVE-MVP-001",
) -> dict:
    asset_reports = []
    checksum = hashlib.sha256()
    content_checksum = hashlib.sha256()
    for asset in sorted(assets):
        files = list_asset_files(data_root, asset)
        inspection = inspect_ohlcv_window(data_root, asset, start=start, end=end)
        for csv_path in files:
            checksum.update(str(csv_path.name).encode("utf-8"))
            checksum.update(str(csv_path.stat().st_size).encode("utf-8"))
        content_checksum.update(asset.encode("utf-8"))
        content_checksum.update(inspection["content_checksum"].encode("ascii"))
        asset_reports.append(
            {
                "asset": asset,
                "source_directory": str(data_root / DEFAULT_ASSET_DIRECTORIES[asset]),
                "file_count": len(files),
                "first_file": files[0].name,
                "last_file": files[-1].name,
                "loaded_bar_count": inspection["bar_count"],
                "loaded_start": inspection["observed_start"],
                "loaded_end": inspection["observed_end"],
                "selected_file_count": inspection["selected_file_count"],
                "content_checksum": inspection["content_checksum"],
                "gap_count": inspection["gap_count"],
                "maximum_gap_seconds": inspection["maximum_gap_seconds"],
                "gap_buckets": inspection["gap_buckets"],
                "gap_policy": inspection["gap_policy"],
                "format": "CSV timestamp,open,high,low,close,volume; UTC timestamps; bid OHLCV export",
            }
        )
    return {
        "data_snapshot_id": snapshot_id,
        "available_at": start,
        "data_root": str(data_root),
        "assets": asset_reports,
        "checksum": checksum.hexdigest(),
        "content_checksum": content_checksum.hexdigest(),
        "point_in_time_policy": "files are read from fixed local paths and filtered by timestamp before signal generation",
    }
