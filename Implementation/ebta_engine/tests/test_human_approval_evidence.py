import unittest

from ebta_engine.governance.human_evidence import (
    approval_evidence_gate,
    evidence_gate,
    manifest_human_evidence,
    normalize_human_approval_evidence,
    normalize_pre_oos_human_evidence,
)


SUBJECTS = {"registry_review": "FAM-001", "pre_oos_approval": "HASH-001"}


class HumanApprovalEvidenceTests(unittest.TestCase):
    def test_absence_is_inconclusive_and_manifest_is_empty(self):
        normalized = normalize_pre_oos_human_evidence(None, expected_subjects=SUBJECTS)
        self.assertEqual(evidence_gate(normalized, "registry_review"), "INCONCLUSIVE")
        self.assertEqual(evidence_gate(normalized, "pre_oos_approval"), "INCONCLUSIVE")
        self.assertEqual(manifest_human_evidence(normalized), ([], []))

    def test_external_evidence_is_bound_to_exact_subjects(self):
        normalized = normalize_pre_oos_human_evidence(
            {
                "registry_review": _entry("REG-APP-001", "FAM-001"),
                "pre_oos_approval": _entry("OOS-APP-001", "HASH-001"),
            },
            expected_subjects=SUBJECTS,
        )
        self.assertTrue(normalized["all_required_approved"])
        self.assertEqual(manifest_human_evidence(normalized), (["REVIEWER-001"], ["REG-APP-001", "OOS-APP-001"]))

    def test_subject_mismatch_cannot_pass(self):
        normalized = normalize_pre_oos_human_evidence(
            {"pre_oos_approval": _entry("OOS-APP-001", "WRONG")},
            expected_subjects=SUBJECTS,
        )
        self.assertEqual(evidence_gate(normalized, "pre_oos_approval"), "INCONCLUSIVE")
        self.assertIn("subject_id_mismatch", normalized["entries"]["pre_oos_approval"]["failures"])

    def test_test_fixture_requires_explicit_option_and_stays_visible(self):
        evidence = {
            "registry_review": _entry("REG-FIXTURE", "FAM-001", scope="test_fixture"),
            "pre_oos_approval": _entry("OOS-FIXTURE", "HASH-001", scope="test_fixture"),
        }
        rejected = normalize_pre_oos_human_evidence(evidence, expected_subjects=SUBJECTS)
        self.assertEqual(evidence_gate(rejected, "pre_oos_approval"), "INCONCLUSIVE")
        accepted = normalize_pre_oos_human_evidence(
            evidence,
            expected_subjects=SUBJECTS,
            allow_test_fixture=True,
        )
        self.assertEqual(
            manifest_human_evidence(accepted),
            (["TEST_FIXTURE:REVIEWER-001"], ["TEST_FIXTURE:REG-FIXTURE", "TEST_FIXTURE:OOS-FIXTURE"]),
        )

    def test_naive_time_and_missing_independence_are_inconclusive(self):
        entry = _entry("OOS-APP-001", "HASH-001")
        entry["approved_at"] = "2026-07-21T12:00:00"
        entry["independence_attested"] = False
        normalized = normalize_pre_oos_human_evidence(
            {"pre_oos_approval": entry},
            expected_subjects=SUBJECTS,
        )
        failures = normalized["entries"]["pre_oos_approval"]["failures"]
        self.assertIn("approved_at_not_utc", failures)
        self.assertIn("independence_not_attested", failures)

    def test_live_approval_is_bound_to_exact_live_version(self):
        accepted = normalize_human_approval_evidence(
            _entry("LIVE-APP-001", "LIVE-001"),
            expected_subject="LIVE-001",
        )
        mismatched = normalize_human_approval_evidence(
            _entry("LIVE-APP-001", "OTHER-LIVE"),
            expected_subject="LIVE-001",
        )

        self.assertEqual(approval_evidence_gate(accepted), "PASS")
        self.assertEqual(approval_evidence_gate(mismatched), "INCONCLUSIVE")
        self.assertIn("subject_id_mismatch", mismatched["failures"])

    def test_live_fixture_requires_explicit_authorization(self):
        evidence = _entry("LIVE-FIXTURE", "LIVE-001", scope="TEST_FIXTURE")

        rejected = normalize_human_approval_evidence(evidence, expected_subject="LIVE-001")
        accepted = normalize_human_approval_evidence(
            evidence,
            expected_subject="LIVE-001",
            allow_test_fixture=True,
        )

        self.assertEqual(approval_evidence_gate(rejected), "INCONCLUSIVE")
        self.assertIn("test_fixture_not_authorized", rejected["failures"])
        self.assertEqual(approval_evidence_gate(accepted), "PASS")


def _entry(evidence_id, subject_id, *, scope="EXTERNAL"):
    return {
        "evidence_id": evidence_id,
        "reviewer_id": "REVIEWER-001",
        "status": "APPROVED",
        "evidence_scope": scope,
        "approved_at": "2026-07-21T12:00:00Z",
        "source_reference": "external://approval-record/001",
        "subject_id": subject_id,
        "independence_attested": True,
    }


if __name__ == "__main__":
    unittest.main()
