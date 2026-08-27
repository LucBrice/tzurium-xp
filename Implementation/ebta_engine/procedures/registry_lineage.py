"""Registry lineage checks.

Source: SOP 03 sections 8, 14, 18, 21, and 22; DN-005 to DN-008, DN-034.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any


def review_registry_lineage(
    registered_candidates: list[str],
    influential_candidates: list[str],
    lineage_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    missing = sorted(set(influential_candidates).difference(registered_candidates))
    unresolved_children = []
    registered = set(registered_candidates)
    for event in lineage_events or []:
        child = event.get("candidate_id")
        parents = set(event.get("parent_candidate_ids", []))
        if child and parents and not parents.issubset(registered):
            unresolved_children.append(event)
    return {
        "artifact_type": "registry_review",
        "status": "PASS" if not missing and not unresolved_children else "FAIL",
        "missing_influential_candidates": missing,
        "unresolved_lineage_events": unresolved_children,
    }

