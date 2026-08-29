"""Offline calibration of execution frictions for the Nautilus MVP.

Source: PLAN_REALISME_ECONOMIQUE_R5_R6, R5.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ebta_engine.data.local_ohlcv import resolve_data_root


CALIBRATION_SCHEMA_VERSION = "1.0.0"
SPREAD_SCALE = 1_000
NASDAQ_TICK_DIRECTORY = "NASDAQ tick"
NASDAQ_TICK_PATTERN = "USATECH.IDXUSD-tick-bid-*.csv"
EXPECTED_NASDAQ_MONTHS = 36
SCENARIO_QUANTILES = {
    "CENTRAL": 0.50,
    "PLAUSIBLE_BASE": 0.95,
    "EXTREME": 0.99,
}
@dataclass(frozen=True)
class TickSpreadScan:
    file_id: str
    sha256: str
    total_rows: int
    valid_rows: int
    invalid_price_rows: int
    crossed_market_rows: int
    spread_frequencies: dict[int, int]


def load_broker_snapshot(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        raise ValueError("an explicit source path is required for the private broker snapshot")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0.0":
        raise ValueError("unsupported broker source schema_version")
    series = payload.get("series")
    if not isinstance(series, dict) or not series:
        raise ValueError("broker source snapshot must define non-empty series")
    for series_id, item in series.items():
        observations = item.get("observations")
        if not isinstance(observations, list) or not observations:
            raise ValueError(f"broker series {series_id} must define observations")
        for observation in observations:
            if not observation.get("broker") or not observation.get("url"):
                raise ValueError(f"broker series {series_id} has incomplete provenance")
            value = float(observation["value"])
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"broker series {series_id} has invalid value")
    return payload


def load_execution_calibration(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        raise ValueError("an explicit calibration path is required for the private calibration")
    calibration_path = path
    payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        raise ValueError("unsupported execution calibration schema_version")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, dict) or set(scenarios) != set(SCENARIO_QUANTILES):
        raise ValueError("execution calibration must define CENTRAL, PLAUSIBLE_BASE, and EXTREME")
    return payload


def scan_nasdaq_tick_file(path: Path, *, data_root: Path) -> TickSpreadScan:
    digest = hashlib.sha256()
    frequencies: Counter[int] = Counter()
    total_rows = 0
    valid_rows = 0
    invalid_price_rows = 0
    crossed_market_rows = 0
    with path.open("rb") as handle:
        header = handle.readline()
        digest.update(header)
        if header.rstrip(b"\r\n") != b"timestamp,ask,bid,ask_volume,bid_volume":
            raise ValueError(f"unexpected NASDAQ tick header: {path.name}")
        for raw_line in handle:
            digest.update(raw_line)
            total_rows += 1
            fields = raw_line.split(b",", 3)
            if len(fields) < 3:
                invalid_price_rows += 1
                continue
            try:
                ask = float(fields[1])
                bid = float(fields[2])
            except ValueError:
                invalid_price_rows += 1
                continue
            if not math.isfinite(ask) or not math.isfinite(bid) or ask <= 0.0 or bid <= 0.0:
                invalid_price_rows += 1
                continue
            if ask < bid:
                crossed_market_rows += 1
                continue
            spread_units = round((ask - bid) * SPREAD_SCALE)
            frequencies[spread_units] += 1
            valid_rows += 1
    return TickSpreadScan(
        file_id=path.relative_to(data_root).as_posix(),
        sha256=digest.hexdigest(),
        total_rows=total_rows,
        valid_rows=valid_rows,
        invalid_price_rows=invalid_price_rows,
        crossed_market_rows=crossed_market_rows,
        spread_frequencies=dict(frequencies),
    )


def quantile_from_frequencies(frequencies: Mapping[int, int], quantile: float) -> float:
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between zero and one")
    total = sum(frequencies.values())
    if total <= 0:
        raise ValueError("spread frequency table is empty")
    target = (total - 1) * quantile
    lower_rank = math.floor(target)
    upper_rank = math.ceil(target)
    lower_value: int | None = None
    upper_value: int | None = None
    seen = 0
    for value, count in sorted(frequencies.items()):
        next_seen = seen + count
        if lower_value is None and lower_rank < next_seen:
            lower_value = value
        if upper_rank < next_seen:
            upper_value = value
            break
        seen = next_seen
    if lower_value is None or upper_value is None:
        raise RuntimeError("quantile ranks were not resolved")
    weight = target - lower_rank
    return ((1.0 - weight) * lower_value + weight * upper_value) / SPREAD_SCALE


def linear_quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(float(value) for value in values)
    target = (len(ordered) - 1) * quantile
    lower = math.floor(target)
    upper = math.ceil(target)
    weight = target - lower
    return (1.0 - weight) * ordered[lower] + weight * ordered[upper]


def broker_series_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    observations = list(item["observations"])
    values = [float(observation["value"]) for observation in observations]
    return {
        "unit": item["unit"],
        "sample_size": len(values),
        "constituents": values,
        "arithmetic_mean": sum(values) / len(values),
        "quantiles": {
            name: linear_quantile(values, quantile)
            for name, quantile in SCENARIO_QUANTILES.items()
        },
        "statistic_kinds": [observation["statistic_kind"] for observation in observations],
        "classification": "BROKER_PROXY",
    }


def build_execution_calibration(
    data_root: Path | str | None = None,
    *,
    source_path: Path | None = None,
) -> dict[str, Any]:
    if source_path is None:
        raise ValueError("an explicit source path is required for the private broker snapshot")
    root = resolve_data_root(data_root)
    source = load_broker_snapshot(source_path)
    tick_root = root / NASDAQ_TICK_DIRECTORY
    files = sorted(tick_root.glob(NASDAQ_TICK_PATTERN))
    if len(files) != EXPECTED_NASDAQ_MONTHS:
        raise ValueError(
            f"expected {EXPECTED_NASDAQ_MONTHS} NASDAQ tick files, found {len(files)} in {tick_root}"
        )

    scans = [scan_nasdaq_tick_file(path, data_root=root) for path in files]
    combined: Counter[int] = Counter()
    for scan in scans:
        combined.update(scan.spread_frequencies)
    local_quantiles = {
        name: quantile_from_frequencies(combined, quantile)
        for name, quantile in SCENARIO_QUANTILES.items()
    }
    broker_summaries = {
        series_id: broker_series_summary(item)
        for series_id, item in source["series"].items()
    }
    latency = broker_summaries["BROKER_EXECUTION_LATENCY_MS"]
    xau_spread = broker_summaries["XAUUSD_SPREAD_POINTS"]
    slippage_probability = broker_summaries["INDEX_ADVERSE_SLIPPAGE_PROBABILITY"]
    commission = broker_summaries["STANDARD_CFD_COMMISSION_RATE"]

    scenarios: dict[str, Any] = {}
    for scenario_name in SCENARIO_QUANTILES:
        scenarios[scenario_name] = {
            "NASDAQ": {
                "spread_points": local_quantiles[scenario_name],
                "spread_provenance": "UNVERIFIED_LOCAL_EXPORT",
                "spread_conversion": "HALF_SPREAD_POINTS_TO_BPS_AT_FILL_PRICE",
                "prob_slippage": slippage_probability["quantiles"][scenario_name],
                "latency_nanos": round(latency["quantiles"][scenario_name] * 1_000_000),
                "commission_rate": commission["quantiles"][scenario_name],
            },
            "XAUUSD": {
                "spread_points": xau_spread["quantiles"][scenario_name],
                "spread_provenance": "BROKER_PROXY",
                "spread_conversion": "HALF_SPREAD_POINTS_TO_BPS_AT_FILL_PRICE",
                "prob_slippage": slippage_probability["quantiles"][scenario_name],
                "latency_nanos": round(latency["quantiles"][scenario_name] * 1_000_000),
                "commission_rate": commission["quantiles"][scenario_name],
            },
        }

    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    total_rows = sum(scan.total_rows for scan in scans)
    valid_rows = sum(scan.valid_rows for scan in scans)
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "as_of_date": source["retrieved_at"],
        "source_snapshot": {
            "file_id": source_path.name,
            "sha256": source_hash,
        },
        "nasdaq_local": {
            "classification": "UNVERIFIED_LOCAL_EXPORT",
            "period": {"start": "2023-01-01", "end": "2025-12-31"},
            "directory_id": NASDAQ_TICK_DIRECTORY,
            "file_count": len(scans),
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "invalid_price_rows": sum(scan.invalid_price_rows for scan in scans),
            "crossed_market_rows": sum(scan.crossed_market_rows for scan in scans),
            "spread_unit": "index_point",
            "spread_scale": SPREAD_SCALE,
            "quantile_method": "linear_interpolation_on_exact_decimal_frequency_table",
            "quantiles": local_quantiles,
            "files": [
                {
                    "file_id": scan.file_id,
                    "sha256": scan.sha256,
                    "total_rows": scan.total_rows,
                    "valid_rows": scan.valid_rows,
                    "invalid_price_rows": scan.invalid_price_rows,
                    "crossed_market_rows": scan.crossed_market_rows,
                }
                for scan in scans
            ],
        },
        "broker_proxy": broker_summaries,
        "scenarios": scenarios,
        "limitations": [
            "The NASDAQ local export has no externally attested provider provenance.",
            "Broker samples mix published averages, minimums, medians, and bounds; cross-broker quantiles are descriptive proxies with small N.",
            "Broker latency is not end-to-end latency from the EBTA execution machine.",
            "The adverse slippage probability is an aggregate IG index-stop proxy, not an asset-specific observed distribution.",
            "Published overall fill rates are retained as evidence but are not mapped to prob_fill_on_limit because the contracts are not equivalent.",
            "XAUUSD spread is BROKER_PROXY because no local ask/bid tick source is available.",
        ],
    }


def calibration_report(payload: Mapping[str, Any]) -> str:
    local = payload["nasdaq_local"]
    broker = payload["broker_proxy"]
    lines = [
        "# R5/R6 execution calibration",
        "",
        f"As of: {payload['as_of_date']}",
        "",
        "## NASDAQ local tick evidence",
        "",
        f"- Classification: `{local['classification']}`",
        f"- Period: {local['period']['start']} to {local['period']['end']}",
        f"- Files: {local['file_count']}",
        f"- Rows: {local['valid_rows']} valid / {local['total_rows']} total",
        f"- Invalid prices: {local['invalid_price_rows']}",
        f"- Crossed markets: {local['crossed_market_rows']}",
        f"- Spread p50/p95/p99 (points): {local['quantiles']['CENTRAL']:.6f} / {local['quantiles']['PLAUSIBLE_BASE']:.6f} / {local['quantiles']['EXTREME']:.6f}",
        "",
        "## Descriptive broker proxies",
        "",
        "| Series | N | Mean | p50 | p95 | p99 | Unit |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for series_id, summary in broker.items():
        lines.append(
            f"| {series_id} | {summary['sample_size']} | {summary['arithmetic_mean']:.6f} | "
            f"{summary['quantiles']['CENTRAL']:.6f} | {summary['quantiles']['PLAUSIBLE_BASE']:.6f} | "
            f"{summary['quantiles']['EXTREME']:.6f} | {summary['unit']} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines.append("")
    return "\n".join(lines)


def write_calibration(payload: Mapping[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "calibration.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "calibration_report.md").write_text(calibration_report(payload), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = build_execution_calibration(args.data_root, source_path=args.source)
    write_calibration(payload, args.output)
    print(json.dumps({"output": str(args.output), "valid_rows": payload["nasdaq_local"]["valid_rows"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
