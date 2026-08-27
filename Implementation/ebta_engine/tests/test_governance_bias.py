import json
import tempfile
import unittest
from typing import Any
from pathlib import Path

from ebta_engine import SUPPORTED_PROTOCOL_VERSIONS
from ebta_engine.governance import (
    append_incident,
    check_candidate_family,
    check_metric_lock,
    check_registry_completeness,
    check_robustness_gate,
    evaluate_bias_gate,
    get_bias_risk,
    guard_oos_access,
    list_bias_risks,
    load_incidents,
    load_open_incidents,
)
from ebta_engine.governance.incident_logger import IncidentLogNotFound, validate_incident
from ebta_engine.schema_validation import validate


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE = ROOT / "governance"


class GovernanceBiasTests(unittest.TestCase):
    def test_runtime_supports_ebta_doc_1_1(self):
        self.assertIn("EBTA-DOC-1.1", SUPPORTED_PROTOCOL_VERSIONS)

    def test_bias_registry_entries_validate_against_schema(self):
        schema = json.loads((GOVERNANCE / "bias_risk_schema.json").read_text(encoding="utf-8"))
        risks = list_bias_risks()

        self.assertEqual(len(risks), 20)
        self.assertEqual({risk["bias_id"] for risk in risks}, {f"BIAS-{index:03d}" for index in range(1, 21)})
        for risk in risks:
            with self.subTest(risk=risk["bias_id"]):
                self.assertEqual(validate(risk, schema), [])
                self.assertEqual(risk["sop_reference"], "SOP 13")
                self.assertIn("G-BIAS", risk["impacted_gates"])

    def test_get_bias_risk_returns_copy(self):
        risk = get_bias_risk("BIAS-005")
        risk["name"] = "mutated"

        self.assertEqual(get_bias_risk("BIAS-005")["name"], "Asset cherry-picking")

    def test_incident_schema_rejects_missing_required_field(self):
        incident = _valid_incident()
        del incident["incident_id"]

        errors = validate_incident(incident)

        self.assertTrue(any(error.path == "$.incident_id" for error in errors))

    def test_incident_logger_appends_without_rewriting_existing_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "INCIDENT_BIAS.jsonl"
            first = append_incident(_valid_incident("BIAS-2026-0001"), log_path)
            first_line = log_path.read_text(encoding="utf-8").splitlines()[0]
            second_payload = _valid_incident("BIAS-2026-0002")
            second_payload["candidate_id"] = "CANDIDATE-002"

            second = append_incident(second_payload, log_path)
            lines = log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], first_line)
        self.assertEqual(json.loads(lines[0])["incident_id"], first["incident_id"])
        self.assertEqual(json.loads(lines[1])["incident_id"], second["incident_id"])

    def test_incident_logger_filters_and_loads_open_blocking_incidents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "INCIDENT_BIAS.jsonl"
            append_incident(_valid_incident("BIAS-2026-0001"), log_path)
            resolved = _valid_incident("BIAS-2026-0002")
            resolved["status"] = "RESOLVED"
            resolved["severity"] = "LEVEL_1"
            resolved["candidate_id"] = "CANDIDATE-002"
            append_incident(resolved, log_path)

            family_incidents = load_incidents(log_path, research_family_id="FAMILY-001")
            open_blocking = load_open_incidents(log_path, min_blocking_severity=True)

        self.assertEqual(len(family_incidents), 2)
        self.assertEqual([incident["incident_id"] for incident in open_blocking], ["BIAS-2026-0001"])

    def test_incident_logger_missing_log_raises_instead_of_reporting_empty(self):
        # Adversarial regression (Lot 4, PLAN_ADVERSARIAL_TESTER_GOUVERNANCE_OUTILLE):
        # a missing/never-created/deleted incident log must never be silently
        # indistinguishable from a verified-clean incident history. Before
        # this fix, load_incidents(missing_path) returned [] - identical to
        # what a genuinely clean log produces - which would let a wrong path
        # or a deleted append-only log masquerade as "no incidents ever
        # happened" to any future G-BIAS caller.
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "does_not_exist.jsonl"

            with self.assertRaises(IncidentLogNotFound):
                load_incidents(missing_path)
            with self.assertRaises(IncidentLogNotFound):
                load_open_incidents(missing_path)

    def test_incident_logger_existing_empty_log_returns_empty_list(self):
        # Positive control for the fix above: a log file that genuinely
        # exists and is empty is a verified-clean state and must still
        # return [] without raising - only a missing path is an error.
        with tempfile.TemporaryDirectory() as temp_dir:
            empty_path = Path(temp_dir) / "empty.jsonl"
            empty_path.touch()

            self.assertEqual(load_incidents(empty_path), [])
            self.assertEqual(load_open_incidents(empty_path), [])

    def test_derogation_schema_validates_required_contract(self):
        schema = json.loads((GOVERNANCE / "derogation_schema.json").read_text(encoding="utf-8"))
        derogation = _valid_derogation()

        self.assertEqual(validate(derogation, schema), [])
        del derogation["approved_by"]
        self.assertTrue(any(error.path == "$.approved_by" for error in validate(derogation, schema)))

    def test_registry_checker_detects_unlogged_run(self):
        report = check_registry_completeness(
            [_registry_event("RUN-001", "CAND-001")],
            _family_matrix(["CAND-001"]),
            expected_run_ids=["RUN-001", "RUN-002"],
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertIn("EXPECTED_RUN_UNLOGGED", {violation["rule"] for violation in report["violations"]})

    def test_candidate_family_checker_detects_missing_candidate(self):
        report = check_candidate_family([_registry_event("RUN-001", "CAND-001")], _family_matrix(["CAND-002"]))

        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "CANDIDATES_MISSING_FROM_STATISTICAL_MATRIX",
            {violation["rule"] for violation in report["violations"]},
        )

    def test_candidate_family_checker_detects_removed_asset(self):
        matrix = _family_matrix(["CAND-001", "CAND-002"])
        matrix["candidate_assets"] = {"CAND-001": "EURUSD", "CAND-002": "EURUSD"}

        report = check_candidate_family([_registry_event("RUN-001", "CAND-001"), _registry_event("RUN-002", "CAND-002")], matrix)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn("ASSETS_REMOVED_FROM_MATRIX", {violation["rule"] for violation in report["violations"]})

    def test_metric_lock_checker_detects_primary_metric_change(self):
        executed = _decision_lock()
        executed["primary_metric"] = "post_hoc_sharpe"

        report = check_metric_lock(_decision_lock(), executed)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn("PREREGISTERED_FIELD_CHANGED", {violation["rule"] for violation in report["violations"]})

    def test_robustness_checker_detects_removed_stress_test(self):
        report = check_robustness_gate(
            {"scenarios": [{"stress_id": "ROB-001"}, {"stress_id": "ROB-002"}]},
            {"executed_stress_ids": ["ROB-001"], "status": "PASS"},
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertIn("PREREGISTERED_STRESS_TEST_REMOVED", {violation["rule"] for violation in report["violations"]})

    def test_oos_guard_blocks_if_incident_open(self):
        request = {flag: True for flag in _required_oos_flags()}
        request["open_blocking_incidents"] = True

        report = guard_oos_access(request)

        self.assertEqual(report["status"], "DENIED")
        self.assertIn("no_open_level_2_or_higher_incident", report["missing_requirements"])

    def test_oos_guard_marks_burned_on_unauthorized_access(self):
        report = guard_oos_access({"unauthorized_access_detected": True})

        self.assertEqual(report["status"], "BURNED")
        self.assertEqual(report["incidents"][0]["status"], "BURNED")

    def test_bias_gate_pass_when_all_artifacts_valid(self):
        report = _bias_gate_report()

        self.assertEqual(report["status"], "PASS")

    def test_bias_gate_fails_when_candidate_missing(self):
        report = _bias_gate_report(candidate_registry=[_registry_event("RUN-001", "CAND-001")])

        self.assertEqual(report["status"], "FAIL")

    def test_bias_gate_fails_when_asset_removed(self):
        matrix = _family_matrix(["CAND-001", "CAND-002"])
        matrix["candidate_assets"] = {"CAND-001": "EURUSD", "CAND-002": "EURUSD"}

        report = _bias_gate_report(statistical_family_matrix=matrix)

        self.assertEqual(report["status"], "FAIL")

    def test_bias_gate_fails_when_primary_metric_changed(self):
        executed = _decision_lock()
        executed["primary_metric"] = "post_hoc_metric"

        report = _bias_gate_report(executed_configuration=executed)

        self.assertEqual(report["status"], "FAIL")

    def test_bias_gate_inconclusive_when_artifact_missing(self):
        report = _bias_gate_report(candidate_registry=None)

        self.assertEqual(report["status"], "INCONCLUSIVE")

    def test_bias_gate_burned_when_oos_access_is_unauthorized(self):
        report = _bias_gate_report(oos_access_log=[{"unauthorized_access_detected": True}])

        self.assertEqual(report["status"], "BURNED")


def _valid_incident(incident_id: str = "BIAS-2026-0001") -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "incident_id": incident_id,
        "timestamp": "2026-07-01T12:00:00+00:00",
        "project_id": "PROJECT-001",
        "research_family_id": "FAMILY-001",
        "candidate_id": "CANDIDATE-001",
        "fold_id": "FOLD-001",
        "phase": "TEST_PRE_OOS",
        "bias_id": "BIAS-005",
        "bias_type": "ASSET_CHERRY_PICKING",
        "detected_by": "candidate_family_checker",
        "evidence_path": "reports/candidate_matrix.json",
        "severity": "LEVEL_2",
        "oos_state": "SEALED",
        "decision": "BLOCK_OOS_AND_RECALCULATE_WRC",
        "reviewer": None,
        "status": "OPEN",
    }


def _valid_derogation() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "derogation_id": "DEROG-2026-0001",
        "timestamp": "2026-07-01T12:00:00+00:00",
        "project_id": "PROJECT-001",
        "research_family_id": "FAMILY-001",
        "phase": "TEST_PRE_OOS",
        "affected_decision": "primary_metric",
        "justification": "Pre-OOS correction to a documented transcription error.",
        "approved_by": "independent_reviewer",
        "approval_timestamp": "2026-07-01T13:00:00+00:00",
        "non_repair_confirmed": True,
        "status": "APPROVED",
    }


def _registry_event(run_id: str, candidate_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "config_hash": "CONFIG-HASH",
        "code_hash": "CODE-HASH",
        "data_hash": "DATA-HASH",
        "decision_status": "PASS",
    }


def _family_matrix(candidate_ids: list[str]) -> dict[str, object]:
    assets = ["EURUSD", "XAUUSD"]
    return {
        "candidate_ids": candidate_ids,
        "applicable_candidates": candidate_ids,
        "asset_universe": assets,
        "candidate_assets": {
            candidate_id: assets[index % len(assets)]
            for index, candidate_id in enumerate(candidate_ids)
        },
    }


def _decision_lock() -> dict[str, object]:
    return {
        "primary_metric": "mean_net_detrended_log_return",
        "secondary_metrics": ["stability", "turnover"],
        "economic_hurdle": {"min_annualized_return": 0.1},
        "benchmark": "cash_plus_benchmark_returns",
        "cost_model": "tradable_net",
        "slippage_model": "fixed_spread",
        "execution_assumptions": {"central_scenario": "tradable_net"},
    }


def _robustness_plan() -> dict[str, object]:
    return {"scenarios": [{"stress_id": "ROB-001"}, {"stress_id": "ROB-002"}]}


def _robustness_report() -> dict[str, object]:
    return {"executed_stress_ids": ["ROB-001", "ROB-002"], "status": "PASS"}


def _required_oos_flags() -> tuple[str, ...]:
    return (
        "pre_oos_sealed",
        "code_hash_frozen",
        "data_hash_frozen",
        "config_frozen",
        "wrc_pass",
        "robustness_pass",
        "registry_complete",
        "bias_gate_pass",
        "reviewer_registered",
    )


def _bias_gate_report(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, Any] = {
        "candidate_registry": [_registry_event("RUN-001", "CAND-001"), _registry_event("RUN-002", "CAND-002")],
        "statistical_family_matrix": _family_matrix(["CAND-001", "CAND-002"]),
        "preregistration_manifest": _decision_lock(),
        "executed_configuration": _decision_lock(),
        "robustness_plan": _robustness_plan(),
        "robustness_matrix": _robustness_report(),
        "oos_access_log": [{"access_event_id": "OOS-001"}],
        "incident_log": [],
        "reviewer_report": {"independent_reviewer": "reviewer", "status": "PASS"},
    }
    kwargs.update(overrides)
    return evaluate_bias_gate(**kwargs)


if __name__ == "__main__":
    unittest.main()
