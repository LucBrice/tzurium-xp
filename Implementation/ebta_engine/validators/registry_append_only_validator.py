"""Append-only registry validator.

Source: Protocole/PAQUET D'EXECUTION EBTA.md section 3.2; SOP 03; DN-005 to
DN-008.
Type: CONTRACT_ENCODING.

This validator enforces the append-only invariant of the EBTA experiment
registry. The registry must never have events deleted, candidates silently
removed, or the universe retrospectively reduced. A chain_hash column links
each event to its predecessor, allowing external verifiers to detect tampering.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_append_only_registry(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate that a registry event list satisfies EBTA append-only rules.

    Parameters
    ----------
    events:
        Ordered list of registry event dicts, each conforming to the
        ``experiment_registry_event.schema.json`` schema.  The list must be
        sorted chronologically (oldest event first).

    Returns
    -------
    dict
        Report with ``status`` (PASS | FAIL | INCONCLUSIVE), violation list,
        and chain integrity result.
    """
    if not events:
        return _inconclusive("empty_event_list")

    violations: list[dict[str, Any]] = []

    # Rule 1 — chain_hash must be present on every event (schema already
    # requires it, but we verify at runtime too).
    missing_chain = [
        event.get("event_id", f"index_{idx}")
        for idx, event in enumerate(events)
        if not event.get("chain_hash")
    ]
    if missing_chain:
        violations.append({
            "rule": "DN-005_CHAIN_HASH_REQUIRED",
            "authority": "SOP 03 / DN-005",
            "event_ids": missing_chain,
            "description": "Every registry event must carry a chain_hash.",
        })

    # Rule 2 — chain_hash integrity: each event hash must cover its
    # predecessor's chain_hash, producing a verifiable chain.
    chain_violations = _check_chain_integrity(events)
    violations.extend(chain_violations)

    # Rule 3 — No retrospective deduplication: if the same candidate_id
    # appears in multiple events, the later event must not silently reduce
    # or replace prior information without a lineage reference (DN-006).
    dedup_violations = _check_no_retrospective_deduplication(events)
    violations.extend(dedup_violations)

    # Rule 4 — Influential candidates must not disappear: once a candidate_id
    # appears with a decision_status that implies it influenced a family
    # selection, it must remain in subsequent events that reference the same
    # research_family_id (DN-007).
    family_violations = _check_family_completeness(events)
    violations.extend(family_violations)

    return {
        "artifact_type": "append_only_registry_report",
        "source_normative": "PAQUET D'EXECUTION §3.2; SOP 03; DN-005 to DN-008",
        "event_count": len(events),
        "status": "PASS" if not violations else "FAIL",
        "violations": violations,
    }


def compute_event_chain_hash(
    event: dict[str, Any],
    previous_chain_hash: str,
) -> str:
    """Compute the expected chain_hash for a single registry event.

    The hash covers: previous_chain_hash + event_id + timestamp +
    candidate_id + decision_status + sorted(output_hashes).

    This function is provided as a reference implementation so that
    external producers can generate a compliant chain_hash.
    """
    payload = json.dumps(
        {
            "previous_chain_hash": previous_chain_hash,
            "event_id": event.get("event_id", ""),
            "timestamp": event.get("timestamp", ""),
            "candidate_id": event.get("candidate_id", ""),
            "decision_status": event.get("decision_status", ""),
            "output_hashes": sorted(event.get("output_hashes") or []),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Statuses that indicate a candidate influenced a family selection decision.
_INFLUENTIAL_STATUSES = frozenset({
    "SELECTED",
    "EVALUATED",
    "APPLICABLE",
    "INFLUENTIAL",
    "IN_FAMILY",
})

# Genesis sentinel — the chain starts from this value for the first event.
_GENESIS_HASH = "0" * 64


def _check_chain_integrity(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Verify that each event's chain_hash matches the expected value."""
    violations: list[dict[str, Any]] = []
    previous = _GENESIS_HASH
    for idx, event in enumerate(events):
        expected = compute_event_chain_hash(event, previous)
        actual = event.get("chain_hash", "")
        if actual != expected:
            violations.append({
                "rule": "DN-005_CHAIN_HASH_INTEGRITY",
                "authority": "SOP 03 / DN-005",
                "event_index": idx,
                "event_id": event.get("event_id", f"index_{idx}"),
                "expected_hash": expected,
                "actual_hash": actual,
                "description": (
                    "chain_hash does not match the expected value computed "
                    "from the previous event and the current event payload."
                ),
            })
        previous = actual or expected
    return violations


def _check_no_retrospective_deduplication(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect candidate_ids that appear, then vanish without a lineage ref."""
    violations: list[dict[str, Any]] = []
    seen: dict[str, int] = {}  # candidate_id -> first index where seen
    for idx, event in enumerate(events):
        candidate_id = event.get("candidate_id", "")
        if not candidate_id:
            continue
        if candidate_id not in seen:
            seen[candidate_id] = idx
        # A retrospective deduplication would manifest as a later event with
        # the same candidate_id but a parent_event_id that differs from the
        # first appearance, and no decision_status that signals a legitimate
        # new run.  We flag the absence of parent linkage as a risk marker
        # rather than a hard FAIL, because the exact deduplication procedure
        # is researcher-configurable (DN-006 says it must be pre-registered).
        parent = event.get("parent_event_id")
        first_idx = seen[candidate_id]
        if idx > first_idx and not parent:
            violations.append({
                "rule": "DN-006_DEDUPLICATION_REQUIRES_LINEAGE",
                "authority": "SOP 03 / DN-006",
                "event_index": idx,
                "candidate_id": candidate_id,
                "first_seen_index": first_idx,
                "description": (
                    "A candidate that already appeared in the registry is "
                    "referenced again without a parent_event_id. If this is "
                    "a legitimate re-run, add the parent_event_id. If this "
                    "is a deduplication, it must be pre-registered and "
                    "performed ex ante only."
                ),
            })
    return violations


def _check_family_completeness(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect influential candidates that are absent from their family WRC."""
    violations: list[dict[str, Any]] = []
    # Build a map: research_family_id -> set of influential candidate_ids
    family_candidates: dict[str, set[str]] = {}
    # Detect WRC events to check family coverage
    for event in events:
        family_id = event.get("research_family_id", "")
        candidate_id = event.get("candidate_id", "")
        status = event.get("decision_status", "")
        if not family_id or not candidate_id:
            continue
        if status.upper() in _INFLUENTIAL_STATUSES:
            family_candidates.setdefault(family_id, set()).add(candidate_id)
    # A WRC event should declare which candidates were included in the matrix.
    # We flag families where the event log shows influential candidates but no
    # WRC_MATRIX_CANDIDATES evidence field is present.
    for event in events:
        event_type = event.get("event_type", "").upper()
        if "WRC" not in event_type:
            continue
        family_id = event.get("research_family_id", "")
        if not family_id:
            continue
        influential = family_candidates.get(family_id, set())
        wrc_candidates = set(event.get("wrc_matrix_candidate_ids") or [])
        if influential and not wrc_candidates:
            violations.append({
                "rule": "DN-008_WRC_FAMILY_COMPLETENESS",
                "authority": "SOP 02 / DN-008",
                "research_family_id": family_id,
                "influential_candidates": sorted(influential),
                "description": (
                    "A WRC event is present but the field "
                    "'wrc_matrix_candidate_ids' is missing or empty. The WRC "
                    "must cover the complete applicable family (DN-008)."
                ),
            })
        elif wrc_candidates:
            missing = influential - wrc_candidates
            if missing:
                violations.append({
                    "rule": "DN-008_WRC_FAMILY_COMPLETENESS",
                    "authority": "SOP 02 / DN-008",
                    "research_family_id": family_id,
                    "missing_from_wrc_matrix": sorted(missing),
                    "description": (
                        "Influential candidates are absent from the WRC "
                        "matrix. The complete applicable family must be "
                        "included (DN-008)."
                    ),
                })
    return violations


def _inconclusive(reason: str) -> dict[str, Any]:
    return {
        "artifact_type": "append_only_registry_report",
        "source_normative": "PAQUET D'EXECUTION §3.2; SOP 03; DN-005 to DN-008",
        "event_count": 0,
        "status": "INCONCLUSIVE",
        "violations": [{"rule": "MISSING_EVIDENCE", "description": reason}],
    }
