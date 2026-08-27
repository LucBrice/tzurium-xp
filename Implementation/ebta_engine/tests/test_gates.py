import unittest
from typing import cast

from ebta_engine.constants import ALL_DECISION_STATUSES
from ebta_engine.validators.gate_validator import (
    GATE_REQUIREMENTS,
    GateRequirement,
    RequirementKind,
    _requirement_satisfied,
    validate_gates,
)


class GateTests(unittest.TestCase):
    def test_gate_report_marks_missing_evidence(self):
        evidence = {
            "config_id": "CFG",
            "project_id": "PRJ",
            "research_family_id": "FAM",
            "hypothesis_id": "HYP",
            "process_version_id": "PROC",
            "template_hash": "HASH",
        }
        results = {result.gate_id: result for result in validate_gates(evidence)}
        self.assertEqual(results["G0"].status, "PASS")
        self.assertEqual(results["G1"].status, "INCONCLUSIVE")
        self.assertEqual(results["G1"].missing, ["data_snapshots", "availability_timestamps", "anti_leakage_report"])

    def test_gate_report_rejects_non_pass_wrc_verdict(self):
        evidence = _complete_evidence()
        evidence["wrc_status"] = "FAIL"

        results = {result.gate_id: result for result in validate_gates(evidence)}

        self.assertNotEqual(results["G4"].status, "PASS")
        self.assertIn("wrc_status", results["G4"].missing)

    def test_gate_report_rejects_non_pass_robustness_verdict(self):
        evidence = _complete_evidence()
        evidence["pre_oos_robustness_verdict"] = "FAIL"

        results = {result.gate_id: result for result in validate_gates(evidence)}

        self.assertNotEqual(results["G5"].status, "PASS")
        self.assertIn("pre_oos_robustness_verdict", results["G5"].missing)

    def test_gate_report_rejects_non_pass_oos_gate(self):
        for verdict in ("FAIL", "INCONCLUSIVE"):
            with self.subTest(verdict=verdict):
                evidence = _complete_evidence()
                evidence["oos_report"] = verdict

                results = {result.gate_id: result for result in validate_gates(evidence)}

                self.assertNotEqual(results["G9"].status, "PASS")
                self.assertIn("oos_report", results["G9"].missing)

    def test_gate_report_rejects_non_pass_data_availability_gate(self):
        self._assert_gate_rejects_non_pass("G1", "data_snapshots")

    def test_gate_report_rejects_non_pass_sealing_gate(self):
        self._assert_gate_rejects_non_pass("G7", "pre_oos_manifest")

    def test_gate_report_rejects_non_pass_validation_ready_gate(self):
        self._assert_gate_rejects_non_pass("G11", "validation_ready_manifest")

    def test_gate_report_rejects_non_pass_incubation_report_gate(self):
        self._assert_gate_rejects_non_pass("G12", "incubation_report")

    def test_gate_report_rejects_non_pass_paper_trading_log_gate(self):
        self._assert_gate_rejects_non_pass("G12", "paper_trading_log")

    def test_gate_report_rejects_non_pass_monitoring_plan_gate(self):
        self._assert_gate_rejects_non_pass("G12", "monitoring_plan")

    def test_gate_report_rejects_non_pass_deployment_certified_gate(self):
        self._assert_gate_rejects_non_pass("G13", "deployment_certified_manifest")

    def test_gate_report_rejects_raw_not_validated_oos_gate(self):
        evidence = _complete_evidence()
        evidence["oos_report"] = "NOT_VALIDATED"

        results = {result.gate_id: result for result in validate_gates(evidence)}

        self.assertEqual(results["G9"].status, "INCONCLUSIVE")
        self.assertIn("oos_report", results["G9"].missing)

    def test_verdict_contract_rejects_all_negative_taxonomies_and_unknown_strings(self):
        rejected_values = (ALL_DECISION_STATUSES - {"PASS"}) | {
            "AUTHORIZED",
            "BURNED",
            "DENIED",
            "UNKNOWN",
            "pass",
            " PASS ",
        }
        requirement = GateRequirement("oos_report", "verdict_pass")

        for value in sorted(rejected_values):
            with self.subTest(value=value):
                self.assertFalse(_requirement_satisfied(requirement, value))

    def test_verdict_contract_rejects_wrong_types(self):
        requirement = GateRequirement("oos_report", "verdict_pass")

        for value in (None, False, True, 0, 1, [], {}):
            with self.subTest(value=value):
                self.assertFalse(_requirement_satisfied(requirement, value))

    def test_identifier_contract_requires_non_empty_string_after_strip(self):
        requirement = GateRequirement("config_id", "identifier")

        self.assertTrue(_requirement_satisfied(requirement, " CFG-001 "))
        for value in (None, False, True, 0, 1, "", "   ", [], {}):
            with self.subTest(value=value):
                self.assertFalse(_requirement_satisfied(requirement, value))

    def test_boolean_contract_accepts_only_true_singleton(self):
        requirement = GateRequirement("live_approval", "boolean_true")

        self.assertTrue(_requirement_satisfied(requirement, True))
        for value in (None, False, 0, 1, "True", "PASS", [], {}):
            with self.subTest(value=value):
                self.assertFalse(_requirement_satisfied(requirement, value))

    def test_unknown_requirement_kind_fails_closed(self):
        requirement = GateRequirement("future_field", cast(RequirementKind, "unknown"))

        with self.assertRaisesRegex(ValueError, "Unknown gate requirement kind"):
            _requirement_satisfied(requirement, "PASS")

    def test_all_gate_requirements_have_the_expected_kind(self):
        identifier_fields = {
            "config_id",
            "project_id",
            "research_family_id",
            "hypothesis_id",
            "process_version_id",
            "template_hash",
            "selected_candidate_id",
            "live_version_id",
        }
        requirements = [requirement for gate in GATE_REQUIREMENTS.values() for requirement in gate]
        names = [requirement.name for requirement in requirements]

        self.assertEqual(list(GATE_REQUIREMENTS), [f"G{index}" for index in range(15)])
        self.assertEqual(len(names), len(set(names)))
        for requirement in requirements:
            with self.subTest(name=requirement.name):
                if requirement.name in identifier_fields:
                    self.assertEqual(requirement.kind, "identifier")
                elif requirement.name == "live_approval":
                    self.assertEqual(requirement.kind, "boolean_true")
                else:
                    self.assertEqual(requirement.kind, "verdict_pass")

    def test_gate_result_preserves_requirement_order(self):
        results = validate_gates({})

        self.assertEqual([result.gate_id for result in results], [f"G{index}" for index in range(15)])
        for result in results:
            self.assertEqual(result.present, [])
            self.assertEqual(result.missing, [requirement.name for requirement in GATE_REQUIREMENTS[result.gate_id]])

    def _assert_gate_rejects_non_pass(self, gate_id: str, field_name: str) -> None:
        for verdict in ("FAIL", "INCONCLUSIVE"):
            with self.subTest(gate_id=gate_id, field_name=field_name, verdict=verdict):
                evidence = _complete_evidence()
                evidence[field_name] = verdict

                results = {result.gate_id: result for result in validate_gates(evidence)}

                self.assertNotEqual(results[gate_id].status, "PASS")
                self.assertIn(field_name, results[gate_id].missing)


def _complete_evidence() -> dict[str, object]:
    values = {
        "identifier": "ID-001",
        "verdict_pass": "PASS",
        "boolean_true": True,
    }
    return {
        requirement.name: values[requirement.kind]
        for requirements in GATE_REQUIREMENTS.values()
        for requirement in requirements
    }


if __name__ == "__main__":
    unittest.main()
