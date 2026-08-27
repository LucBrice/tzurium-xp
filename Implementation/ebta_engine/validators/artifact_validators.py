"""Schema-backed validators for EBTA artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ebta_engine.schema_validation import ValidationError, validate

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validate_json_file(path: Path, schema_name: str) -> list[ValidationError]:
    return validate(json.loads(path.read_text(encoding="utf-8")), load_schema(schema_name))


def validate_jsonl_file(path: Path, schema_name: str) -> list[ValidationError]:
    schema = load_schema(schema_name)
    errors: list[ValidationError] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        errors.extend(
            ValidationError(f"line {line_no} {error.path}", error.message)
            for error in validate(json.loads(line), schema)
        )
    return errors
