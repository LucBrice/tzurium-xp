"""Validation of optional human approval evidence.

Source: PLAN_CONTRAT_APPROBATIONS_HUMAINES_POST_OOS, decision 3A.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


EVIDENCE_KEYS = ("registry_review", "pre_oos_approval")
VALID_SCOPES = frozenset({"EXTERNAL", "TEST_FIXTURE"})


def normalize_pre_oos_human_evidence(
    payload: Mapping[str, Any] | None,
    *,
    expected_subjects: Mapping[str, str],
    allow_test_fixture: bool = False,
) -> dict[str, Any]:
    source = payload if isinstance(payload, Mapping) else {}
    entries = {
        key: _normalize_entry(
            source.get(key),
            expected_subject=str(expected_subjects[key]),
            allow_test_fixture=allow_test_fixture,
        )
        for key in EVIDENCE_KEYS
    }
    return {
        "schema_version": "1.0.0",
        "entries": entries,
        "all_required_approved": all(entry["decision_status"] == "PASS" for entry in entries.values()),
    }


def evidence_gate(normalized: Mapping[str, Any], key: str) -> str:
    entry = normalized.get("entries", {}).get(key, {})
    return approval_evidence_gate(entry)


def approval_evidence_gate(normalized_entry: Mapping[str, Any]) -> str:
    status = normalized_entry.get("decision_status")
    return status if status in {"PASS", "FAIL", "INCONCLUSIVE"} else "INCONCLUSIVE"


def normalize_human_approval_evidence(
    payload: Mapping[str, Any] | None,
    *,
    expected_subject: str,
    allow_test_fixture: bool = False,
) -> dict[str, Any]:
    """Normalize one approval without creating an identity or positive default."""

    return _normalize_entry(
        payload,
        expected_subject=expected_subject,
        allow_test_fixture=allow_test_fixture,
    )


def manifest_human_evidence(normalized: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    reviewers: list[str] = []
    approvals: list[str] = []
    for key in EVIDENCE_KEYS:
        entry = normalized.get("entries", {}).get(key, {})
        if entry.get("decision_status") != "PASS":
            continue
        prefix = "TEST_FIXTURE:" if entry.get("evidence_scope") == "TEST_FIXTURE" else ""
        reviewer = prefix + str(entry["reviewer_id"])
        approval = prefix + str(entry["evidence_id"])
        if reviewer not in reviewers:
            reviewers.append(reviewer)
        approvals.append(approval)
    return reviewers, approvals


def _normalize_entry(
    value: Any,
    *,
    expected_subject: str,
    allow_test_fixture: bool,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "decision_status": "INCONCLUSIVE",
            "failures": ["missing_evidence"],
            "expected_subject_id": expected_subject,
        }
    fields = {
        name: value.get(name)
        for name in (
            "evidence_id",
            "reviewer_id",
            "status",
            "evidence_scope",
            "approved_at",
            "source_reference",
            "subject_id",
            "independence_attested",
        )
    }
    failures: list[str] = []
    for name in (
        "evidence_id",
        "reviewer_id",
        "status",
        "evidence_scope",
        "approved_at",
        "source_reference",
        "subject_id",
    ):
        if not isinstance(fields[name], str) or not str(fields[name]).strip():
            failures.append(f"missing_{name}")
    scope = str(fields.get("evidence_scope") or "").upper()
    status = str(fields.get("status") or "").upper()
    if scope not in VALID_SCOPES:
        failures.append("invalid_evidence_scope")
    elif scope == "TEST_FIXTURE" and not allow_test_fixture:
        failures.append("test_fixture_not_authorized")
    if fields.get("subject_id") != expected_subject:
        failures.append("subject_id_mismatch")
    if fields.get("independence_attested") is not True:
        failures.append("independence_not_attested")
    approved_at = fields.get("approved_at")
    if isinstance(approved_at, str) and approved_at.strip() and not _is_utc_timestamp(approved_at):
        failures.append("approved_at_not_utc")
    if status != "APPROVED":
        failures.append("status_not_approved")

    decision_status = "FAIL" if status == "REJECTED" else "INCONCLUSIVE"
    if not failures:
        decision_status = "PASS"
    normalized: dict[str, Any] = {
        "decision_status": decision_status,
        "failures": failures,
        "expected_subject_id": expected_subject,
    }
    for name, field_value in fields.items():
        if isinstance(field_value, (str, bool)):
            normalized[name] = field_value.strip() if isinstance(field_value, str) else field_value
    normalized["status"] = status
    normalized["evidence_scope"] = scope
    return normalized


def _is_utc_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)
