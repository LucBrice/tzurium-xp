"""Train-side optimization logging and representative selection.

Source: SOP 06 sections 9, 10, 11, 13, and 23.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any

from ebta_engine.procedures._utils import require_not_oos


def optimize_on_train(
    search_space: dict[str, Any],
    train_scores: dict[str, float],
    *,
    train_segment: str = "Train_k",
    objective: str = "maximize",
) -> dict[str, Any]:
    require_not_oos(train_segment)
    if objective not in {"maximize", "minimize"}:
        raise ValueError("objective must be 'maximize' or 'minimize'")

    reverse = objective == "maximize"
    log = []
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for candidate in search_space["candidates"]:
        candidate_id = candidate["candidate_id"]
        score = train_scores.get(candidate_id)
        entry = {
            "candidate_id": candidate_id,
            "complexity": candidate.get("complexity", 0),
            "train_score": score,
            "status": "EVALUATED" if score is not None else "MISSING_TRAIN_SCORE",
        }
        log.append(entry)
        if score is not None:
            grouped.setdefault(candidate.get("complexity", 0), []).append(entry)

    representatives = []
    for _complexity, entries in sorted(grouped.items(), key=lambda item: item[0]):
        ordered = sorted(entries, key=lambda item: (item["train_score"], item["candidate_id"]), reverse=reverse)
        representatives.append({**ordered[0], "representative_rule": "best_train_score_per_complexity"})

    return {
        "artifact_type": "optimization_log",
        "source_segment": train_segment,
        "objective": objective,
        "research_family_id": search_space["research_family_id"],
        "fold_id": search_space["fold_id"],
        "evaluations": sorted(log, key=lambda item: item["candidate_id"]),
        "representatives": representatives,
    }
