"""Zero-centering for Test-side WRC H0 construction.

Source: SOP 07 sections 15 and 17; SOP 02 section 8; DN-018.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations


def zero_center_columns(candidate_series: dict[str, list[float]]) -> dict:
    if not candidate_series:
        raise ValueError("zero-centering requires at least one candidate")
    centered = {}
    means = {}
    for candidate_id, values in sorted(candidate_series.items()):
        if not values:
            raise ValueError(f"candidate series is empty: {candidate_id}")
        mean_value = sum(values) / len(values)
        means[candidate_id] = mean_value
        centered[candidate_id] = [float(value) - mean_value for value in values]
    return {
        "artifact_type": "zero_centered_matrix",
        "column_means": means,
        "centered_series": centered,
    }


def assert_not_oos_zero_centering(segment_id: str) -> None:
    if "OOS" in segment_id.upper():
        raise ValueError("OOS series must not be zero-centered for estimation")

