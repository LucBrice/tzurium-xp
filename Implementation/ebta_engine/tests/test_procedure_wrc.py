import unittest

from ebta_engine.procedures.bootstrap import resample_columns, stationary_block_indices
from ebta_engine.procedures.wrc import mcpm_permutation_test, wrc_test
from ebta_engine.procedures.zero_centering import assert_not_oos_zero_centering, zero_center_columns


class WrcProcedureTests(unittest.TestCase):
    def test_zero_centering_centers_each_column(self):
        report = zero_center_columns({"CAND-A": [1.0, 2.0, 3.0], "CAND-B": [-1.0, 1.0, 0.0]})
        for values in report["centered_series"].values():
            self.assertAlmostEqual(sum(values), 0.0)
        with self.assertRaises(ValueError):
            assert_not_oos_zero_centering("OOS_k")

    def test_stationary_bootstrap_indices_are_reproducible_and_common(self):
        first = stationary_block_indices(5, replications=3, mean_block_length=2, seed=11)
        second = stationary_block_indices(5, replications=3, mean_block_length=2, seed=11)
        self.assertEqual(first, second)
        resampled = resample_columns({"A": [10, 20, 30, 40, 50], "B": [1, 2, 3, 4, 5]}, first[0])
        self.assertEqual(len(resampled["A"]), len(resampled["B"]))
        self.assertEqual([value // 10 for value in resampled["A"]], resampled["B"])

    def test_wrc_uses_complete_family_and_fixed_seed(self):
        matrix = {
            "CAND-A": [0.04, 0.03, 0.05, 0.04],
            "CAND-B": [-0.01, 0.00, -0.02, 0.01],
        }
        first = wrc_test(matrix, replications=19, mean_block_length=2, seed=17, alpha=0.10)
        second = wrc_test(matrix, replications=19, mean_block_length=2, seed=17, alpha=0.10)
        self.assertEqual(first["bootstrap_distribution"], second["bootstrap_distribution"])
        self.assertEqual(first["verdict"], "PASS")
        self.assertTrue(first["secondary_tests_cannot_override_wrc"])
        self.assertEqual(first["secondary_tests"]["spa"]["status"], "EXECUTED_SECONDARY")
        self.assertEqual(first["secondary_tests"]["romano_wolf"]["status"], "EXECUTED_SECONDARY")
        self.assertEqual(
            first["secondary_tests"]["mcpm"]["status"],
            "BLOCKED_REQUIRES_PREREGISTERED_CAUSAL_RECALCULATION",
        )
        self.assertEqual(first["power_diagnostics"]["status"], "DIAGNOSTIC_ONLY")

    def test_wrc_rejects_winner_only_matrix(self):
        with self.assertRaises(ValueError):
            wrc_test({"CAND-WINNER": [0.1, 0.2]}, replications=10, mean_block_length=2, seed=1)

    def test_secondary_tests_do_not_reverse_failed_wrc(self):
        matrix = {
            "CAND-A": [0.001, -0.001, 0.001, -0.001],
            "CAND-B": [-0.001, 0.001, -0.001, 0.001],
        }
        report = wrc_test(matrix, replications=19, mean_block_length=2, seed=17, alpha=0.01)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(
            report["secondary_tests"]["romano_wolf"]["status"],
            "NOT_APPLICABLE_PRIMARY_WRC_NOT_PASS",
        )
        self.assertTrue(report["secondary_tests"]["spa"]["cannot_override_wrc"])

    def test_mcpm_requires_preregistered_causal_recalculation(self):
        matrix = {"CAND-A": [0.01, 0.02], "CAND-B": [0.0, -0.01]}
        report = mcpm_permutation_test(matrix, [[0, 1], [1, 0]], alpha=0.05, permutation_scheme=None, recalculator=None)
        self.assertEqual(report["status"], "BLOCKED_REQUIRES_PREREGISTERED_CAUSAL_RECALCULATION")


if __name__ == "__main__":
    unittest.main()
