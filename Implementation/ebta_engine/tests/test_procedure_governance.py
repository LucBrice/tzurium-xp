import unittest
from datetime import datetime, timezone

from ebta_engine.procedures.data_availability import validate_availability
from ebta_engine.procedures.economic_gate import economic_gate_report
from ebta_engine.procedures.lifecycle import deployment_gate, incubation_gate
from ebta_engine.procedures.oos_access import authorize_oos_access
from ebta_engine.procedures.registry_lineage import review_registry_lineage
from ebta_engine.procedures.robustness import robustness_verdict
from ebta_engine.procedures.sealing import validate_pre_oos_seal
from ebta_engine.procedures.walk_forward import validate_walk_forward_schedule


class GovernanceProcedureTests(unittest.TestCase):
    def test_data_availability_blocks_future_data(self):
        report = validate_availability(
            [{"available_at": "2026-01-02T00:00:00Z", "decision_at": "2026-01-01T00:00:00Z"}]
        )
        self.assertEqual(report["status"], "FAIL")

    def test_walk_forward_rejects_overlapping_oos(self):
        report = validate_walk_forward_schedule(
            [
                {"fold_id": "F1", "train": ["2020-01-01", "2020-12-31"], "test": ["2021-01-01", "2021-06-30"], "oos": ["2021-07-01", "2021-12-31"]},
                {"fold_id": "F2", "train": ["2020-07-01", "2021-06-30"], "test": ["2021-07-01", "2021-12-31"], "oos": ["2021-12-01", "2022-06-30"]},
            ]
        )
        self.assertEqual(report["status"], "FAIL")

    def test_registry_lineage_detects_missing_influential_candidate(self):
        report = review_registry_lineage(["CAND-A"], ["CAND-A", "CAND-B"])
        self.assertEqual(report["missing_influential_candidates"], ["CAND-B"])

    def test_robustness_rejects_oos_consumption(self):
        report = robustness_verdict([{"stress_id": "S1", "uses_observed_oos": True, "blocking": True, "scenario_verdict": "PASS"}])
        self.assertEqual(report["status"], "FAIL")

    def test_oos_access_requires_pre_oos_seal(self):
        denied = authorize_oos_access({"pre_oos_sealed": False})
        self.assertEqual(denied["status"], "DENIED")
        before = datetime.now(timezone.utc)
        seal = validate_pre_oos_seal("PRE_OOS_SEALED", manifest_hash="HASH", independent_approval=True)
        after = datetime.now(timezone.utc)
        self.assertEqual(seal["status"], "PASS")
        sealed_at = datetime.fromisoformat(seal["sealed_at"].replace("Z", "+00:00"))
        self.assertLessEqual(before, sealed_at)
        self.assertLessEqual(sealed_at, after)
        self.assertEqual(seal["sealed_at_source"], "RUNTIME_UTC")

    def test_pre_oos_seal_uses_injected_fixture_clock(self):
        fixture_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

        seal = validate_pre_oos_seal(
            "PRE_OOS_SEALED",
            manifest_hash="HASH",
            independent_approval=True,
            clock=lambda: fixture_time,
        )

        self.assertEqual(seal["sealed_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(seal["sealed_at_source"], "INJECTED_FIXTURE_CLOCK")

    def test_failed_pre_oos_seal_has_no_timestamp(self):
        seal = validate_pre_oos_seal(
            "DRAFT",
            manifest_hash="",
            independent_approval=False,
            clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(seal["status"], "FAIL")
        self.assertNotIn("sealed_at", seal)
        self.assertNotIn("sealed_at_source", seal)

    def test_pre_oos_seal_rejects_naive_clock(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            validate_pre_oos_seal(
                "PRE_OOS_SEALED",
                manifest_hash="HASH",
                independent_approval=True,
                clock=lambda: datetime(2026, 1, 1),
            )

    def test_oos_access_authorizes_only_after_bias_gate_pass(self):
        authorized = authorize_oos_access(
            {
                "access_event_id": "OOS-001",
                "timestamp": "2026-07-01T00:00:00Z",
                "actor": "tester",
                "fold_id": "FOLD-001",
                "oos_segment_id": "OOS-001",
                "pre_oos_sealed": True,
                "wrc_pass": True,
                "robustness_pass": True,
                "execution_pass": True,
                "independent_approval": True,
                "bias_gate_pass": True,
            }
        )

        self.assertEqual(authorized["status"], "AUTHORIZED")

        denied = authorize_oos_access({**authorized["log_entry"], "pre_oos_sealed": True})
        self.assertIn("bias_gate_pass", denied["missing_requirements"])

    def test_economic_gate_remains_separate_from_statistical_gate(self):
        report = economic_gate_report(
            {
                "statistical_status": "PASS",
                "return_hurdle_pass": True,
                "drawdown_pass": True,
                "capacity_pass": False,
                "costs_pass": True,
                "execution_pass": True,
            }
        )
        self.assertEqual(report["economic_status"], "REJECTED_ECONOMIC")
        self.assertEqual(report["global_status"], "REJECTED_ECONOMIC")

    def test_lifecycle_requires_validation_ready_before_incubation(self):
        incubation = incubation_gate(
            {
                "statistical_status": "PASS",
                "economic_status": "PASS",
                "robustness_status": "PASS",
                "execution_status": "PASS",
                "package_stage": "PRE_OOS_SEALED",
                "reproduction_status": "PASS",
            }
        )
        self.assertEqual(incubation["status"], "FAIL")
        deployment = deployment_gate(
            {
                "paper_trading_status": "PASS",
                "package_stage": "DEPLOYMENT_CERTIFIED",
                "kill_switch_tested": True,
                "live_deployment_status": "PASS",
                "live_approval_status": "PASS",
            }
        )
        self.assertEqual(deployment["status"], "PASS")

        for field in ("live_deployment_status", "live_approval_status"):
            with self.subTest(field=field):
                rejected = deployment_gate(
                    {
                        "paper_trading_status": "PASS",
                        "package_stage": "DEPLOYMENT_CERTIFIED",
                        "kill_switch_tested": True,
                        "live_deployment_status": "PASS",
                        "live_approval_status": "PASS",
                        field: "INCONCLUSIVE",
                    }
                )
                self.assertEqual(rejected["status"], "FAIL")
                self.assertIn(field, rejected["failures"])


if __name__ == "__main__":
    unittest.main()
