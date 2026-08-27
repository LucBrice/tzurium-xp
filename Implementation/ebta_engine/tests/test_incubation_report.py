import unittest
from typing import Any

from ebta_engine.procedures.incubation_report import validate_live_deployment_report


class LiveDeploymentReportTests(unittest.TestCase):
    def test_exact_pass_verdict_is_required(self):
        for verdict in ("FAIL", "INCONCLUSIVE", "WATCH", "SUSPENDED", "UNKNOWN", "pass", None):
            with self.subTest(verdict=verdict):
                report = _valid_live_report()
                report["verdict"] = verdict

                result = validate_live_deployment_report(report)

                self.assertEqual(result["status"], "FAIL")
                self.assertNotEqual(result["status"], "PASS")

    def test_valid_live_report_with_pass_verdict_passes(self):
        result = validate_live_deployment_report(_valid_live_report())

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["submitted_verdict"], "PASS")

    def test_empty_live_report_is_inconclusive(self):
        result = validate_live_deployment_report({})

        self.assertEqual(result["status"], "INCONCLUSIVE")


def _valid_live_report() -> dict[str, Any]:
    return {
        "report_id": "LIVE-REPORT-001",
        "config_id": "CFG-001",
        "package_stage": "DEPLOYMENT_CERTIFIED",
        "live_version_id": "LIVE-001",
        "capital_deployed": 100_000,
        "capital_limit": 1_000_000,
        "sizing_policy_applied": True,
        "kill_switch_tested": True,
        "monitoring_plan_id": "MON-001",
        "verdict": "PASS",
    }


if __name__ == "__main__":
    unittest.main()
