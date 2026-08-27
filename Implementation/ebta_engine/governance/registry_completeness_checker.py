"""Registry completeness checker for EBTA G-BIAS.

Source: SOP 03; SOP 13; DN-005 to DN-008; DN-042.
Type: CONTRACT_ENCODING.
"""

from __future__ import annotations

from typing import Any


REQUIRED_RUN_FIELDS = ("run_id", "candidate_id")
REQUIRED_HASH_MARKERS = ("config_hash", "code_hash", "data_hash")
PRESERVED_STATUS_MARKERS = {"FAIL", "FAILED", "INTERRUPTED", "ERROR", "REJECTED", "NOT_SELECTED"}


def check_registry_completeness(
    registry_events: list[dict[str, Any]],
    statistical_family_matrix: dict[str, Any] | None = None,
    *,
    expected_run_ids: list[str] | None = None,
    expected_candidate_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Detect missing runs, candidates, hashes, and matrix coverage."""
    if not registry_events:
        return _report("INCONCLUSIVE", [{"rule": "REGISTRY_MISSING", "bias_id": "BIAS-006"}])

    violations: list[dict[str, Any]] = []
    for index, event in enumerate(registry_events):
        for field in REQUIRED_RUN_FIELDS:
            if not event.get(field):
                violations.append({
                    "rule": "RUN_FIELD_MISSING",
                    "event_index": index,
                    "field": field,
                    "bias_id": "BIAS-004",
                    "description": f"Registry event is missing {field}.",
                })
        available_hashes = _hash_markers(event)
        for marker in REQUIRED_HASH_MARKERS:
            if marker not in available_hashes:
                violations.append({
                    "rule": "RUN_HASH_MISSING",
                    "event_index": index,
                    "field": marker,
                    "bias_id": "BIAS-002",
                    "description": f"Registry event is missing {marker}.",
                })

    registered_runs = {event.get("run_id") for event in registry_events if event.get("run_id")}
    registered_candidates = {event.get("candidate_id") for event in registry_events if event.get("candidate_id")}

    if expected_run_ids:
        missing_runs = sorted(set(expected_run_ids) - registered_runs)
        if missing_runs:
            violations.append({
                "rule": "EXPECTED_RUN_UNLOGGED",
                "missing_run_ids": missing_runs,
                "bias_id": "BIAS-006",
                "description": "Executed or expected runs are missing from the append-only registry.",
            })

    matrix_candidates = _matrix_candidates(statistical_family_matrix or {})
    expected_candidates = set(expected_candidate_ids or []) | matrix_candidates
    missing_candidates = sorted(expected_candidates - registered_candidates)
    if missing_candidates:
        violations.append({
            "rule": "CANDIDATES_MISSING_FROM_REGISTRY",
            "missing_candidate_ids": missing_candidates,
            "bias_id": "BIAS-004",
            "description": "Candidates used by the statistical family are missing from the registry.",
        })

    if matrix_candidates and registered_candidates and len(matrix_candidates) != len(registered_candidates):
        violations.append({
            "rule": "REGISTRY_MATRIX_COUNT_MISMATCH",
            "registry_candidate_count": len(registered_candidates),
            "matrix_candidate_count": len(matrix_candidates),
            "bias_id": "BIAS-006",
            "description": "Registry candidate count differs from statistical family matrix count.",
        })

    preserved = [
        event for event in registry_events
        if str(event.get("decision_status", "")).upper() in PRESERVED_STATUS_MARKERS
    ]
    if expected_run_ids and not preserved and any("FAIL" in run_id.upper() for run_id in expected_run_ids):
        violations.append({
            "rule": "FAILED_RUNS_NOT_PRESERVED",
            "bias_id": "BIAS-006",
            "description": "Expected failed or interrupted runs are not preserved in the registry.",
        })

    return _report("PASS" if not violations else "FAIL", violations)


def _hash_markers(event: dict[str, Any]) -> set[str]:
    markers: set[str] = set()
    for marker in REQUIRED_HASH_MARKERS:
        if event.get(marker):
            markers.add(marker)
    for field in ("input_hashes", "output_hashes"):
        for value in event.get(field) or []:
            key = str(value).split(":", 1)[0]
            if key in REQUIRED_HASH_MARKERS:
                markers.add(key)
    return markers


def _matrix_candidates(matrix: dict[str, Any]) -> set[str]:
    for key in ("candidate_ids", "wrc_matrix_candidates", "applicable_candidates"):
        if matrix.get(key):
            return set(matrix[key])
    return set()


def _report(status: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    incidents = [
        {
            "bias_id": violation.get("bias_id", "BIAS-006"),
            "severity": "LEVEL_2",
            "status": "OPEN",
            "decision": "BLOCK_OOS_AND_RECONCILE_REGISTRY",
            "evidence_path": "registry.jsonl",
            "description": violation.get("description", violation["rule"]),
        }
        for violation in violations
    ]
    return {
        "artifact_type": "registry_completeness_report",
        "source_normative": "SOP 03; SOP 13; DN-005 to DN-008",
        "status": status,
        "violations": violations,
        "incidents": incidents,
    }
