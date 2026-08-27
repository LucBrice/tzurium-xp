"""Shared helpers for EBTA procedures."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_id(prefix: str, payload: Any, length: int = 12) -> str:
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest().upper()
    return f"{prefix}-{digest[:length]}"


def require_not_oos(segment_name: str) -> None:
    if "OOS" in segment_name.upper():
        raise ValueError("OOS input is forbidden for selection, optimization, or tie-break procedures")

