import unittest

from ebta_engine.procedures.robustness import pre_oos_robustness_verdict
from ebta_engine.risk.robustness import compute_robustness_scenarios
from ebta_engine.strategy_api.contracts import SimulationResult


class RiskRobustnessTests(unittest.TestCase):
    def test_computed_scenarios_are_consumed_by_procedure_validator(self):
        result = SimulationResult(
            candidate_id="CAND-1",
            instrument_id="NASDAQ.SIM",
            timestamps=["2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z"],
            daily_returns=[0.01, 0.02],
            daily_exposure=[0.1, 0.1],
            nav=[1000.0, 1020.0],
            total_costs=0.0,
        )
        grid = {
            "scenarios": [
                {
                    "stress_id": "ROB-CENTRAL",
                    "classification": "CENTRAL",
                    "blocking": True,
                    "minimum_mean_return": 0.0,
                },
                {
                    "stress_id": "ROB-PLAUSIBLE",
                    "classification": "PLAUSIBLE_BASE",
                    "blocking": True,
                    "minimum_mean_return": 0.0,
                },
                {
                    "stress_id": "ROB-EXTREME",
                    "classification": "EXTREME",
                    "blocking": False,
                    "minimum_mean_return": 0.0,
                },
            ]
        }

        scenarios = compute_robustness_scenarios(
            {
                "ROB-CENTRAL": [result],
                "ROB-PLAUSIBLE": [result],
                "ROB-EXTREME": [result],
            },
            scenario_grid=grid,
        )
        verdict = pre_oos_robustness_verdict(scenarios)

        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual({scenario["classification"] for scenario in scenarios}, {"CENTRAL", "PLAUSIBLE_BASE", "EXTREME"})
        for scenario in scenarios:
            self.assertIn("stress_id", scenario)
            self.assertIn("scenario_verdict", scenario)
            self.assertIn("blocking", scenario)

    def test_missing_threshold_is_inconclusive_not_invented(self):
        result = SimulationResult(
            candidate_id="CAND-1",
            instrument_id="NASDAQ.SIM",
            timestamps=["2020-01-01T00:00:00Z"],
            daily_returns=[0.01],
            daily_exposure=[0.1],
            nav=[1000.0],
            total_costs=0.0,
        )
        scenarios = compute_robustness_scenarios(
            {"ROB-CENTRAL": [result]},
            scenario_grid={"scenarios": [{"stress_id": "ROB-CENTRAL", "classification": "CENTRAL", "blocking": True}]},
        )
        verdict = pre_oos_robustness_verdict(scenarios)

        self.assertEqual(scenarios[0]["scenario_verdict"], "INCONCLUSIVE")
        self.assertEqual(verdict["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
