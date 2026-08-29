"""Append-only G-BIAS incident logger.

Source: SOP 13; Protocole/TEMPLATE - Incident de biais EBTA.md.
Type: CONTRACT_ENCODING.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ebta_engine.schema_validation import ValidationError, validate


# Kept as a compatibility export, but deliberately unusable as an implicit
# destination.  An installed library must never write inside its environment.
DEFAULT_INCIDENT_LOG: None = None
SCHEMA_PATH = Path(__file__).with_name("incident_schema.json")
INCIDENT_SCHEMA_VERSION = "1.0.0"
BLOCKING_SEVERITIES = {"LEVEL_2", "LEVEL_3", "LEVEL_4", "LEVEL_5"}
OPEN_STATUSES = {"OPEN", "FAIL", "INCONCLUSIVE", "BURNED"}


def append_incident(
    incident: dict[str, Any],
    log_path: Path | str | None = None,
) -> dict[str, Any]:
    """Validate and append one incident as a JSONL row.

    The function only appends. It never rewrites, truncates, sorts, or removes
    existing incidents.
    """
    normalized = _normalize_incident(incident)
    errors = validate_incident(normalized)
    if errors:
        details = "; ".join(f"{error.path}: {error.message}" for error in errors)
        raise ValueError(f"Invalid G-BIAS incident: {details}")

    target = _explicit_log_path(log_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n")
    return normalized


class IncidentLogNotFound(FileNotFoundError):
    """Raised when an incident log path does not exist.

    Deliberately distinct from an empty result. A log file that exists and
    contains zero lines means "verified: no incidents were ever recorded" -
    a legitimate, confirmed state. A log file that does not exist at all
    means "we cannot verify the incident history" (never created, wrong
    path, or deleted). Collapsing both into the same [] return value would
    let a missing or mistyped path masquerade as a verified-clean incident
    history to any G-BIAS caller - exactly the silent-fallback pattern
    SOP 13 / .agents/skills/adversarial-tester exist to catch. Callers that
    need "treat unknown as no incidents" must opt into that explicitly by
    catching this exception, rather than receiving it implicitly.
    """


def load_incidents(
    log_path: Path | str | None = None,
    **filters: str,
) -> list[dict[str, Any]]:
    """Load incidents from JSONL, optionally filtering by exact field values.

    Raises IncidentLogNotFound if the log file does not exist (see that
    exception's docstring for why this is not the same as an empty log).
    """
    target = _explicit_log_path(log_path)
    if not target.exists():
        raise IncidentLogNotFound(f"Incident log not found: {target}")

    incidents: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            incident = json.loads(line)
            errors = validate_incident(incident)
            if errors:
                details = "; ".join(f"{error.path}: {error.message}" for error in errors)
                raise ValueError(f"Invalid incident at line {line_number}: {details}")
            if _matches_filters(incident, filters):
                incidents.append(incident)
    return incidents


def load_open_incidents(
    log_path: Path | str | None = None,
    min_blocking_severity: bool = False,
    **filters: str,
) -> list[dict[str, Any]]:
    """Load incidents whose status can block G-BIAS."""
    incidents = load_incidents(log_path, **filters)
    open_incidents = [incident for incident in incidents if incident["status"] in OPEN_STATUSES]
    if min_blocking_severity:
        return [incident for incident in open_incidents if incident["severity"] in BLOCKING_SEVERITIES]
    return open_incidents


def validate_incident(incident: dict[str, Any]) -> list[ValidationError]:
    """Validate an incident against the EBTA G-BIAS incident schema."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return validate(incident, schema)


def _normalize_incident(incident: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(incident)
    normalized.setdefault("schema_version", INCIDENT_SCHEMA_VERSION)
    normalized.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    return normalized


def _matches_filters(incident: dict[str, Any], filters: dict[str, str]) -> bool:
    return all(incident.get(field) == expected for field, expected in filters.items())


def _explicit_log_path(log_path: Path | str | None) -> Path:
    if log_path is None:
        raise ValueError("an explicit log_path is required; installed packages have no writable default")
    return Path(log_path)
