"""Smoke-test the installed distribution from outside the source checkout."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from importlib.resources import files
from pathlib import Path

import ebta_engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forbid-root", type=Path, required=True)
    args = parser.parse_args()

    module_path = Path(ebta_engine.__file__).resolve()
    forbidden_root = args.forbid_root.resolve()
    if module_path.is_relative_to(forbidden_root):
        raise AssertionError(f"ebta_engine resolved from source checkout: {module_path}")

    distribution = importlib.metadata.distribution("tzurium-xp-ebta-engine")
    if distribution.version != "0.0.0":
        raise AssertionError(f"unexpected distribution version: {distribution.version}")
    notice_entries = [
        item for item in (distribution.files or ()) if item.as_posix().endswith("licenses/NOTICE")
    ]
    if len(notice_entries) != 1:
        raise AssertionError(f"expected one installed NOTICE, found: {notice_entries}")
    notice_path = Path(str(distribution.locate_file(notice_entries[0])))
    notice_text = notice_path.read_text(encoding="utf-8")
    if "Copyright 2026 TZURIUM XP" not in notice_text:
        raise AssertionError("installed NOTICE does not contain the authorized copyright line")

    package_root = files("ebta_engine")
    required_resources = (
        "schemas/config.schema.json",
        "governance/incident_schema.json",
        "fixtures/valid_minimal/config.json",
        "fixtures/valid_minimal/registry.jsonl",
        "fixtures/valid_minimal/reports/gates.json",
        "fixtures/valid_minimal/series/oos_primary_returns.json",
    )
    for relative_path in required_resources:
        resource = package_root
        for part in relative_path.split("/"):
            resource = resource.joinpath(part)
        payload = resource.read_text(encoding="utf-8")
        if relative_path.endswith((".json", ".schema.json")):
            json.loads(payload)

    source_package = forbidden_root / "Implementation" / "ebta_engine"
    expected_data = {
        path.relative_to(source_package).as_posix()
        for path in source_package.rglob("*")
        if path.is_file() and path.suffix in {".json", ".jsonl"}
    }
    installed_root = module_path.parent
    installed_data = {
        path.relative_to(installed_root).as_posix()
        for path in installed_root.rglob("*")
        if path.is_file() and path.suffix in {".json", ".jsonl"}
    }
    if installed_data != expected_data:
        raise AssertionError(
            "installed resource mismatch: "
            f"missing={sorted(expected_data - installed_data)}, "
            f"extra={sorted(installed_data - expected_data)}"
        )

    print(
        json.dumps(
            {
                "distribution": distribution.metadata["Name"],
                "module_path": str(module_path),
                "resources_checked": len(installed_data),
                "version": distribution.version,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
