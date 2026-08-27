"""Stationary bootstrap helpers.

Source: SOP 02 sections 7 and 9; SOP 07 section 16; SOP 01 / DN-020 for
separate OOS bootstrap use.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

import random


def stationary_block_indices(
    length: int,
    *,
    replications: int,
    mean_block_length: float,
    seed: int,
) -> list[list[int]]:
    if length <= 0:
        raise ValueError("length must be positive")
    if replications <= 0:
        raise ValueError("replications must be positive")
    if mean_block_length <= 0:
        raise ValueError("mean_block_length must be positive")
    rng = random.Random(seed)
    restart_probability = min(1.0, 1.0 / mean_block_length)
    all_indices = []
    for _ in range(replications):
        current = rng.randrange(length)
        sample = []
        for _ in range(length):
            if sample and rng.random() < restart_probability:
                current = rng.randrange(length)
            sample.append(current)
            current = (current + 1) % length
        all_indices.append(sample)
    return all_indices


def resample_columns(candidate_series: dict[str, list[float]], indices: list[int]) -> dict[str, list[float]]:
    return {
        candidate_id: [values[index] for index in indices]
        for candidate_id, values in sorted(candidate_series.items())
    }

