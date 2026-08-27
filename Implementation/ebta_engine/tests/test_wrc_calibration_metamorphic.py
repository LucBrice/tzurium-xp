"""Deterministic post-audit regression guards for the primary WRC.

These fixtures are deliberately smaller than a real EBTA run.  They detect
gross behavioural drift; they do not certify the WRC type-I error rate and do
not replace SOP 02's preregistered parameters (including B=5000).
"""

import random
import unittest

from ebta_engine.procedures.wrc import wrc_test


def _null_family(data_seed: int) -> dict[str, list[float]]:
    rng = random.Random(data_seed)
    return {
        f"CAND-{candidate_index:02d}": [rng.gauss(0.0, 1.0) for _ in range(252)]
        for candidate_index in range(4)
    }


def _family_expansion_fixture() -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    rng = random.Random(0)
    observation_count = 128
    winner = [0.22 + rng.gauss(0.0, 1.0) for _ in range(observation_count)]
    weak_candidate = [rng.gauss(0.0, 1.0) for _ in range(observation_count)]
    base = {"CAND-A": winner, "CAND-B": weak_candidate}
    added_candidates = {
        f"CAND-X{candidate_index}": [rng.gauss(0.0, 1.0) for _ in range(observation_count)]
        for candidate_index in range(8)
    }
    return base, {**base, **added_candidates}


def _fixture_wrc(candidate_series: dict[str, list[float]]) -> dict:
    return wrc_test(
        candidate_series,
        replications=499,
        mean_block_length=5,
        seed=77,
        alpha=0.05,
        run_secondary=False,
    )


class WrcCalibrationMetamorphicTests(unittest.TestCase):
    def test_seeded_gaussian_null_fixture_does_not_systematically_pass(self):
        """Regression ratchet on 40 fixed null datasets, not a calibration proof."""
        pass_count = 0
        for trial in range(40):
            report = wrc_test(
                _null_family(trial),
                replications=499,
                mean_block_length=5,
                seed=10_000 + trial,
                alpha=0.05,
                run_secondary=False,
            )
            pass_count += report["verdict"] == "PASS"

        self.assertLessEqual(
            pass_count,
            3,
            "The fixed null-regression corpus produced too many WRC PASS verdicts; "
            "audit the implementation instead of changing seeds or weakening this ratchet.",
        )

    def test_candidate_renaming_does_not_change_wrc_result(self):
        base, _ = _family_expansion_fixture()
        renamed = {"RENAMED-X": base["CAND-A"], "RENAMED-Y": base["CAND-B"]}
        base_report = _fixture_wrc(base)
        renamed_report = _fixture_wrc(renamed)

        invariant_fields = (
            "observed_statistic",
            "bootstrap_distribution",
            "exceedance_count",
            "wrc_pvalue",
            "verdict",
        )
        for field in invariant_fields:
            with self.subTest(field=field):
                self.assertEqual(base_report[field], renamed_report[field])

        self.assertNotEqual(base_report["candidate_ids"], renamed_report["candidate_ids"])
        self.assertNotEqual(base_report["family_catalogue_hash"], renamed_report["family_catalogue_hash"])

    def test_controlled_family_expansion_cannot_make_verdict_more_favorable(self):
        base, expanded = _family_expansion_fixture()
        base_report = _fixture_wrc(base)
        expanded_report = _fixture_wrc(expanded)

        self.assertEqual(base_report["verdict"], "PASS")
        self.assertEqual(expanded_report["verdict"], "FAIL")
        self.assertGreaterEqual(expanded_report["wrc_pvalue"], base_report["wrc_pvalue"])


if __name__ == "__main__":
    unittest.main()
