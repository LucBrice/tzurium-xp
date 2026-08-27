"""Deterministic ML manifest builder.

Source: SOP 06 section 16; SOP 09A / DN-026 for Train-only fitting.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any

from ebta_engine.procedures._utils import require_not_oos, stable_id


def build_ml_manifest(
    model_id: str,
    *,
    train_segment: str,
    features: list[str],
    transformations: list[dict[str, Any]],
    hyperparameters: dict[str, Any],
    seeds: list[int],
    complexity_levels: list[int],
    selection_rule: str,
    architecture: str = "deterministic_stub",
    loss_function: str = "primary_metric_surrogate",
) -> dict[str, Any]:
    require_not_oos(train_segment)
    for transformation in transformations:
        if transformation.get("fit_segment") != train_segment:
            raise ValueError("ML transformations must be fit on the declared Train_k segment")
    manifest = {
        "artifact_type": "ml_manifest",
        "model_id": model_id,
        "train_segment": train_segment,
        "features": sorted(features),
        "transformations": transformations,
        "architecture": architecture,
        "hyperparameters": hyperparameters,
        "loss_function": loss_function,
        "seeds": seeds,
        "complexity_levels": complexity_levels,
        "selection_rule": selection_rule,
    }
    manifest["manifest_id"] = stable_id("ML", manifest)
    return manifest

