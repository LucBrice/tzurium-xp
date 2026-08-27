import unittest
from typing import Any, cast

from ebta_engine.procedures.oos_confidence_interval import oos_confidence_interval


class OosConfidenceIntervalTests(unittest.TestCase):
    def test_oos_ci_uses_separate_oos_bootstrap_source(self):
        report = oos_confidence_interval(
            [0.01, 0.02, 0.015, 0.01],
            replications=29,
            mean_block_length=2,
            seed=23,
            pre_oos_development_returns=_pre_oos_returns(),
            min_annualized_return=0.10,
        )
        self.assertEqual(report["source"], "OOS_STATIONARY_BLOCK")
        self.assertEqual(report["statistical_gate"], "PASS")
        self.assertEqual(report["power_check"]["status"], "PASS")
        self.assertEqual(len(report["bootstrap_means"]), 29)

    def test_oos_ci_rejects_wrc_test_distribution(self):
        with self.assertRaises(ValueError):
            oos_confidence_interval(
                [0.01, 0.02],
                replications=10,
                mean_block_length=2,
                seed=1,
                pre_oos_development_returns=_pre_oos_returns(),
                min_annualized_return=0.10,
                bootstrap_source="WRC_TEST_DISTRIBUTION",
            )

    def test_oos_ci_verdicts_are_mechanical(self):
        fail = oos_confidence_interval(
            [-0.01, 0.0],
            replications=10,
            mean_block_length=2,
            seed=3,
            pre_oos_development_returns=_pre_oos_returns(),
            min_annualized_return=0.10,
        )
        self.assertEqual(fail["statistical_gate"], "FAIL")
        inconclusive = oos_confidence_interval(
            [0.01, 0.01],
            replications=10,
            mean_block_length=2,
            seed=3,
            pre_oos_development_returns=_volatile_pre_oos_returns(),
            min_annualized_return=0.10,
        )
        self.assertEqual(inconclusive["statistical_gate"], "INCONCLUSIVE")
        self.assertEqual(inconclusive["power_check"]["status"], "INCONCLUSIVE")

    def test_oos_ci_requires_pre_oos_development_returns_for_power(self):
        report = oos_confidence_interval(
            [0.01, 0.01],
            replications=10,
            mean_block_length=2,
            seed=3,
            pre_oos_development_returns=[0.001, 0.002],
            min_annualized_return=0.10,
        )

        self.assertEqual(report["statistical_gate"], "INCONCLUSIVE")
        self.assertEqual(report["power_check"]["reason"], "insufficient_distinct_pre_oos_blocks")

    def test_oos_ci_power_variance_does_not_use_oos_return_values(self):
        report_a = oos_confidence_interval(
            [0.01, 0.02, 0.015, 0.012],
            replications=20,
            mean_block_length=2,
            seed=3,
            pre_oos_development_returns=_pre_oos_returns(),
            min_annualized_return=0.10,
        )
        report_b = oos_confidence_interval(
            [0.50, 0.40, 0.30, 0.20],
            replications=20,
            mean_block_length=2,
            seed=3,
            pre_oos_development_returns=_pre_oos_returns(),
            min_annualized_return=0.10,
        )

        self.assertEqual(report_a["power_check"]["achieved_power"], report_b["power_check"]["achieved_power"])

    def test_oos_ci_no_longer_accepts_raw_power_override(self):
        dynamic_oos_confidence_interval = cast(Any, oos_confidence_interval)
        with self.assertRaises(TypeError):
            dynamic_oos_confidence_interval(
                [0.01, 0.02, 0.015, 0.01],
                replications=29,
                mean_block_length=2,
                seed=23,
                pre_oos_development_returns=_pre_oos_returns(),
                min_annualized_return=0.10,
                power=0.80,
            )


def _pre_oos_returns() -> list[float]:
    return [0.00050, 0.00055, 0.00052, 0.00057, 0.00051, 0.00056, 0.00053, 0.00058] * 8


def _volatile_pre_oos_returns() -> list[float]:
    return [-0.02, 0.02, -0.015, 0.015, -0.01, 0.01, -0.005, 0.005] * 8


if __name__ == "__main__":
    unittest.main()
