import math
import unittest

from ebta_engine.procedures.detrending import (
    assert_signal_flow_unchanged,
    detrend_returns,
    fit_train_only_transformation,
)
from ebta_engine.procedures.returns import build_daily_return_series, mean_log_return, reconcile_net_pnl


class ReturnAndDetrendingTests(unittest.TestCase):
    def test_daily_net_log_returns_keep_no_exposure_days(self):
        series = build_daily_return_series(
            [
                {"date": "2022-01-03", "nav_open": 100.0, "nav_close": 101.0, "gross_pnl": 1.2, "costs": 0.2},
                {"date": "2022-01-04", "nav_open": 101.0, "nav_close": 101.0, "status": "NO_MODEL"},
            ]
        )
        self.assertEqual(series["row_count"], 2)
        self.assertEqual(series["rows"][1]["status"], "NO_MODEL")
        self.assertAlmostEqual(series["rows"][0]["economic_log_return"], math.log(101.0 / 100.0))
        self.assertTrue(reconcile_net_pnl(series["rows"][0]))

    def test_mean_log_return_uses_declared_field(self):
        rows = [{"detrended_log_return": 0.01}, {"detrended_log_return": -0.005}]
        self.assertAlmostEqual(mean_log_return(rows, "detrended_log_return"), 0.0025)

    def test_detrending_uses_evaluation_segment_drift(self):
        report = detrend_returns(
            [0.03, 0.01],
            [0.02, 0.00],
            [0.001, 0.001],
            [1.0, 0.5],
            segment_id="Test_k",
        )
        self.assertEqual(report["segment_id"], "Test_k")
        self.assertEqual(len(report["detrended_returns"]), 2)
        self.assertAlmostEqual(report["market_drift"], 0.01)

    def test_train_only_transformation_rejects_test_fit(self):
        fitted = fit_train_only_transformation("scaler", [1.0, 2.0], fit_segment="Train_k")
        self.assertEqual(fitted["fit_segment"], "Train_k")
        with self.assertRaises(ValueError):
            fit_train_only_transformation("scaler", [1.0, 2.0], fit_segment="Test_k")

    def test_evaluation_flow_does_not_modify_signal_flow(self):
        signals = ["BUY", "HOLD", "SELL"]
        self.assertTrue(assert_signal_flow_unchanged(signals, list(signals)))
        self.assertFalse(assert_signal_flow_unchanged(signals, ["BUY", "SELL", "SELL"]))


if __name__ == "__main__":
    unittest.main()
