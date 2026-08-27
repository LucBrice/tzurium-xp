"""Test-side complexity selection.

Source: SOP 06 sections 8, 12, 19, and 23.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any

from ebta_engine.procedures._utils import require_not_oos


def select_complexity(
    representatives: list[dict[str, Any]],
    test_scores: dict[str, float],
    *,
    test_segment: str = "Test_k",
    no_model_policy: str = "NO_MODEL",
) -> dict[str, Any]:
    require_not_oos(test_segment)
    admissible = []
    for representative in representatives:
        candidate_id = representative["candidate_id"]
        score = test_scores.get(candidate_id)
        if score is not None:
            admissible.append({**representative, "test_score": score})

    if not admissible:
        return {
            "artifact_type": "complexity_selection",
            "source_segment": test_segment,
            "status": no_model_policy,
            "selected_candidate_id": None,
            "reason": "no admissible candidate with Test_k score",
        }

    max_score = max(item["test_score"] for item in admissible)
    tied = [item for item in admissible if item["test_score"] == max_score]
    ordered = sorted(
        tied,
        key=lambda item: (
            item.get("complexity", 0),
            -item.get("stability", 0),
            item.get("turnover", 0),
            item.get("cost", 0),
            item.get("exposure", 0),
            item["candidate_id"],
        ),
    )
    selected = ordered[0]
    return {
        "artifact_type": "complexity_selection",
        "source_segment": test_segment,
        "status": "PASS",
        "selection_rule": "max_test_score_then_preregistered_tie_breaks",
        "selected_candidate_id": selected["candidate_id"],
        "selected_complexity": selected.get("complexity", 0),
        "test_score": selected["test_score"],
        "tie_break_candidates": [item["candidate_id"] for item in tied],
        "all_test_scores": dict(sorted(test_scores.items())),
    }

