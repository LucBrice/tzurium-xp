"""Candidate-family coverage checker for EBTA G-BIAS."""

from __future__ import annotations

from typing import Any


def check_candidate_family(
    candidate_registry: list[dict[str, Any]] | dict[str, Any],
    statistical_family_matrix: dict[str, Any],
) -> dict[str, Any]:
    """Verify that the statistical family covers all influential candidates."""
    registered = _registered_candidates(candidate_registry)
    matrix_candidates = set(statistical_family_matrix.get("candidate_ids") or [])
    applicable = set(statistical_family_matrix.get("applicable_candidates") or matrix_candidates or registered)
    candidate_assets = statistical_family_matrix.get("candidate_assets") or {}
    asset_universe = set(statistical_family_matrix.get("asset_universe") or [])
    selected = statistical_family_matrix.get("selected_candidate_id")

    if not registered or not matrix_candidates:
        return _report("INCONCLUSIVE", [{"rule": "CANDIDATE_FAMILY_EVIDENCE_MISSING", "bias_id": "BIAS-004"}])

    violations: list[dict[str, Any]] = []
    missing_from_matrix = sorted((registered | applicable) - matrix_candidates)
    if missing_from_matrix:
        violations.append({
            "rule": "CANDIDATES_MISSING_FROM_STATISTICAL_MATRIX",
            "missing_candidate_ids": missing_from_matrix,
            "bias_id": "BIAS-004",
            "description": "Registered or applicable candidates are absent from the statistical family matrix.",
        })

    if selected and matrix_candidates == {selected} and len(registered) > 1:
        violations.append({
            "rule": "MATRIX_CONTAINS_ONLY_WINNER",
            "selected_candidate_id": selected,
            "bias_id": "BIAS-004",
            "description": "Statistical family matrix contains only the selected candidate.",
        })

    if asset_universe:
        if not candidate_assets:
            violations.append({
                "rule": "ASSET_AXIS_MAPPING_MISSING",
                "bias_id": "BIAS-005",
                "description": "Asset universe is declared but candidate asset mapping is absent.",
            })
        else:
            mapped_candidates = set(candidate_assets)
            missing_asset_mapping = sorted(applicable - mapped_candidates)
            if missing_asset_mapping:
                violations.append({
                    "rule": "CANDIDATE_ASSET_MAPPING_MISSING",
                    "missing_candidate_ids": missing_asset_mapping,
                    "bias_id": "BIAS-005",
                    "description": "Applicable strategy x asset candidates are missing asset mapping.",
                })
            covered_assets = {asset for candidate, asset in candidate_assets.items() if candidate in matrix_candidates}
            missing_assets = sorted(asset_universe - covered_assets)
            if missing_assets:
                violations.append({
                    "rule": "ASSETS_REMOVED_FROM_MATRIX",
                    "missing_assets": missing_assets,
                    "bias_id": "BIAS-005",
                    "description": "Declared assets are absent from the statistical family matrix.",
                })

    return _report("PASS" if not violations else "FAIL", violations)


def _registered_candidates(candidate_registry: list[dict[str, Any]] | dict[str, Any]) -> set[str]:
    if isinstance(candidate_registry, dict):
        for key in ("candidate_ids", "registered_candidates", "applicable_candidates"):
            if candidate_registry.get(key):
                return set(candidate_registry[key])
        return set(candidate_registry)
    return {event["candidate_id"] for event in candidate_registry if event.get("candidate_id")}


def _report(status: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    incidents = [
        {
            "bias_id": violation.get("bias_id", "BIAS-004"),
            "severity": "LEVEL_2",
            "status": "OPEN",
            "decision": "BLOCK_OOS_AND_REBUILD_COMPLETE_FAMILY",
            "evidence_path": "reports/candidate_matrix.json",
            "description": violation.get("description", violation["rule"]),
        }
        for violation in violations
    ]
    return {
        "artifact_type": "candidate_family_report",
        "source_normative": "SOP 03; SOP 13; DN-008; DN-043",
        "status": status,
        "violations": violations,
        "incidents": incidents,
    }
