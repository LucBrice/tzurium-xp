"""Executable EBTA invariant checks.

Source: Protocole/PAQUET D'EXECUTION EBTA.md section 6.
Each check consumes explicit package evidence. Missing evidence returns
INCONCLUSIVE instead of inventing a rule.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvariantResult:
    invariant_id: str
    status: str
    message: str


INVARIANT_MAP = {
    "INV-001": {"sop": "SOP 04", "artifact": "oos_segments"},
    "INV-002": {"sop": "SOP 10 / SOP 12", "artifact": "oos_access_log + pre_oos_sealed_at"},
    "INV-003": {"sop": "SOP 02 / SOP 10", "artifact": "oos_openings"},
    "INV-004": {"sop": "SOP 03", "artifact": "influential_candidates + registered_candidates"},
    "INV-005": {"sop": "SOP 02 / SOP 03", "artifact": "wrc_matrix_candidates + applicable_candidates"},
    "INV-006": {"sop": "SOP 09A", "artifact": "transformation_fits"},
    "INV-007": {"sop": "SOP 09A", "artifact": "decision_events"},
    "INV-008": {"sop": "SOP 08", "artifact": "expected_oos_days + oos_series_days"},
    "INV-009": {"sop": "SOP 01 / SOP 02", "artifact": "bootstrap_sources"},
    "INV-010": {"sop": "SOP 08 / SOP 10", "artifact": "gate_reports"},
    "INV-011": {"sop": "SOP 05 / SOP 10", "artifact": "robustness_checks"},
    "INV-012": {"sop": "SOP 10", "artifact": "same_oos_reruns"},
    "INV-013": {"sop": "SOP 03 / SOP 10", "artifact": "influential_modifications"},
    "INV-014": {"sop": "SOP 11 / SOP 12", "artifact": "package_stages"},
    "INV-015": {"sop": "SOP 11 / SOP 12", "artifact": "package_stages"},
    "INV-016": {"sop": "SOP 12", "artifact": "manifest_hash_failures"},
    "INV-017": {"sop": "SOP 03 / SOP 09A", "artifact": "asset_universe + candidate_assets + wrc_matrix_candidates"},
}


def validate_invariants(package: dict) -> list[InvariantResult]:
    results = [
        _inv_001(package),
        _inv_002(package),
        _inv_003(package),
        _inv_004(package),
        _inv_005(package),
        _inv_006(package),
        _inv_007(package),
        _inv_008(package),
        _inv_009(package),
        _inv_010(package),
        _inv_011(package),
        _inv_012(package),
        _inv_013(package),
        _inv_014(package),
        _inv_015(package),
        _inv_016(package),
        _inv_017(package),
    ]
    return sorted(results, key=lambda result: result.invariant_id)


def _inv_001(package: dict) -> InvariantResult:
    segments = package.get("oos_segments", [])
    if not segments:
        return _missing("INV-001", "oos_segments")
    for index, left in enumerate(segments):
        for right in segments[index + 1 :]:
            if left["start"] <= right["end"] and right["start"] <= left["end"]:
                return InvariantResult("INV-001", "FAIL", "OOS segments overlap")
    return InvariantResult("INV-001", "PASS", "OOS segments do not overlap")


def _inv_002(package: dict) -> InvariantResult:
    sealed_at = package.get("pre_oos_sealed_at")
    access_log = package.get("oos_access_log")
    if not sealed_at or access_log is None:
        return _missing("INV-002", "pre_oos_sealed_at or oos_access_log")
    for access in access_log:
        if access["timestamp"] < sealed_at:
            return InvariantResult("INV-002", "FAIL", "OOS access before PRE_OOS_SEALED")
    return InvariantResult("INV-002", "PASS", "no OOS access before PRE_OOS_SEALED")


def _inv_003(package: dict) -> InvariantResult:
    if "oos_openings" not in package:
        return _missing("INV-003", "oos_openings")
    for opening in package.get("oos_openings", []):
        if opening.get("wrc_local_status") != "PASS":
            return InvariantResult("INV-003", "FAIL", "OOS opened after non-PASS WRC")
    return InvariantResult("INV-003", "PASS", "all OOS openings follow WRC PASS")


def _inv_004(package: dict) -> InvariantResult:
    if "influential_candidates" not in package or "registered_candidates" not in package:
        return _missing("INV-004", "influential_candidates or registered_candidates")
    missing = set(package["influential_candidates"]) - set(package["registered_candidates"])
    if missing:
        return InvariantResult("INV-004", "FAIL", f"influential candidates missing from registry: {sorted(missing)}")
    return InvariantResult("INV-004", "PASS", "all influential candidates are registered")


def _inv_005(package: dict) -> InvariantResult:
    if "applicable_candidates" not in package or "wrc_matrix_candidates" not in package:
        return _missing("INV-005", "applicable_candidates or wrc_matrix_candidates")
    missing = set(package["applicable_candidates"]) - set(package["wrc_matrix_candidates"])
    if missing:
        return InvariantResult("INV-005", "FAIL", f"WRC matrix missing candidates: {sorted(missing)}")
    return InvariantResult("INV-005", "PASS", "WRC matrix contains the complete applicable family")


def _inv_006(package: dict) -> InvariantResult:
    if "transformation_fits" not in package:
        return _missing("INV-006", "transformation_fits")
    invalid = [fit for fit in package["transformation_fits"] if fit.get("fit_segment") != "Train_k"]
    if invalid:
        return InvariantResult("INV-006", "FAIL", "learned transformation fitted outside Train_k")
    return InvariantResult("INV-006", "PASS", "learned transformations are fit only on Train_k")


def _inv_007(package: dict) -> InvariantResult:
    if "decision_events" not in package:
        return _missing("INV-007", "decision_events")
    for event in package["decision_events"]:
        if event["data_available_at"] > event["decision_at"]:
            return InvariantResult("INV-007", "FAIL", "decision uses data before operational availability")
    return InvariantResult("INV-007", "PASS", "data availability precedes decisions")


def _inv_008(package: dict) -> InvariantResult:
    if "expected_oos_days" not in package or "oos_series_days" not in package:
        return _missing("INV-008", "expected_oos_days or oos_series_days")
    missing = set(package["expected_oos_days"]) - {day["date"] for day in package["oos_series_days"]}
    if missing:
        return InvariantResult("INV-008", "FAIL", f"OOS series missing days: {sorted(missing)}")
    return InvariantResult("INV-008", "PASS", "OOS series retains all expected days")


def _inv_009(package: dict) -> InvariantResult:
    sources = package.get("bootstrap_sources")
    if not sources:
        return _missing("INV-009", "bootstrap_sources")
    if sources.get("oos") == sources.get("wrc_test"):
        return InvariantResult("INV-009", "FAIL", "OOS bootstrap reuses WRC Test distribution")
    return InvariantResult("INV-009", "PASS", "OOS bootstrap is distinct from WRC Test")


def _inv_010(package: dict) -> InvariantResult:
    reports = package.get("gate_reports")
    if not reports:
        return _missing("INV-010", "gate_reports")
    required = {"statistical", "economic", "final", "final_components"}
    if not required.issubset(reports):
        return InvariantResult("INV-010", "FAIL", "statistical, economic, final, and components must be published")
    statuses = [reports.get(field) for field in ("statistical", "economic", "final")]
    if any(not isinstance(status, str) or not status for status in statuses):
        return InvariantResult("INV-010", "FAIL", "gate report statuses must be non-empty strings")
    components = reports.get("final_components")
    if not isinstance(components, list) or components != ["statistical", "economic"]:
        return InvariantResult("INV-010", "FAIL", "final_components must preserve statistical then economic")
    components_pass = reports["statistical"] == "PASS" and reports["economic"] == "PASS"
    if (reports["final"] == "PASS") != components_pass:
        return InvariantResult("INV-010", "FAIL", "final PASS is inconsistent with statistical and economic components")
    return InvariantResult("INV-010", "PASS", "statistical, economic, and final gate reports are internally coherent")


def _inv_011(package: dict) -> InvariantResult:
    if "robustness_checks" not in package:
        return _missing("INV-011", "robustness_checks")
    if any(check.get("uses_observed_oos") for check in package["robustness_checks"]):
        return InvariantResult("INV-011", "FAIL", "decision robustness uses observed OOS")
    return InvariantResult("INV-011", "PASS", "decision robustness does not use observed OOS")


def _inv_012(package: dict) -> InvariantResult:
    if "same_oos_reruns" not in package:
        return _missing("INV-012", "same_oos_reruns")
    missing = [rerun for rerun in package["same_oos_reruns"] if not rerun.get("post_mortem_id")]
    if missing:
        return InvariantResult("INV-012", "FAIL", "same-OOS rerun without SOP 10 post-mortem")
    return InvariantResult("INV-012", "PASS", "same-OOS reruns have SOP 10 post-mortems")


def _inv_013(package: dict) -> InvariantResult:
    if "influential_modifications" not in package:
        return _missing("INV-013", "influential_modifications")
    invalid = [item for item in package["influential_modifications"] if not item.get("creates_new_candidate_or_version")]
    if invalid:
        return InvariantResult("INV-013", "FAIL", "influential modification without new candidate/version")
    return InvariantResult("INV-013", "PASS", "influential modifications create new candidate/version")


def _inv_014(package: dict) -> InvariantResult:
    stages = package.get("package_stages", [])
    if not stages:
        return _missing("INV-014", "package_stages")
    if "INCUBATION_STARTED" in stages and "VALIDATION_READY" not in stages:
        return InvariantResult("INV-014", "FAIL", "incubation before VALIDATION_READY")
    return InvariantResult("INV-014", "PASS", "VALIDATION_READY precedes incubation or incubation absent")


def _inv_015(package: dict) -> InvariantResult:
    stages = package.get("package_stages", [])
    if not stages:
        return _missing("INV-015", "package_stages")
    if "LIVE_LIMITED_STARTED" in stages and "DEPLOYMENT_CERTIFIED" not in stages:
        return InvariantResult("INV-015", "FAIL", "live before DEPLOYMENT_CERTIFIED")
    return InvariantResult("INV-015", "PASS", "DEPLOYMENT_CERTIFIED precedes live or live absent")


def _inv_016(package: dict) -> InvariantResult:
    if "manifest_hash_failures" not in package:
        return _missing("INV-016", "manifest_hash_failures")
    if package.get("manifest_hash_failures"):
        return InvariantResult("INV-016", "FAIL", "manifest hash mismatch")
    return InvariantResult("INV-016", "PASS", "manifest hashes match")


def _inv_017(package: dict) -> InvariantResult:
    if not package.get("asset_selection_axis"):
        return InvariantResult("INV-017", "PASS", "asset selection axis not active")
    required = {"asset_universe", "candidate_assets", "applicable_candidates", "wrc_matrix_candidates"}
    missing_evidence = sorted(key for key in required if key not in package)
    if missing_evidence:
        return _missing("INV-017", f"asset-axis evidence: {missing_evidence}")
    asset_universe = set(package["asset_universe"])
    candidate_assets = package["candidate_assets"]
    applicable_candidates = set(package["applicable_candidates"])
    wrc_matrix_candidates = set(package["wrc_matrix_candidates"])
    missing_mapping = sorted(applicable_candidates - set(candidate_assets))
    if missing_mapping:
        return InvariantResult("INV-017", "FAIL", f"applicable candidates missing asset mapping: {missing_mapping}")
    unknown_assets = sorted({candidate_assets[candidate_id] for candidate_id in applicable_candidates} - asset_universe)
    if unknown_assets:
        return InvariantResult("INV-017", "FAIL", f"candidate assets outside asset_universe: {unknown_assets}")
    missing_from_wrc = sorted(applicable_candidates - wrc_matrix_candidates)
    if missing_from_wrc:
        return InvariantResult("INV-017", "FAIL", f"WRC matrix missing strategie x actif candidates: {missing_from_wrc}")
    covered_assets = {candidate_assets[candidate_id] for candidate_id in wrc_matrix_candidates if candidate_id in candidate_assets}
    uncovered_assets = sorted(asset_universe - covered_assets)
    if uncovered_assets:
        return InvariantResult("INV-017", "FAIL", f"asset_universe assets missing from WRC matrix: {uncovered_assets}")
    return InvariantResult("INV-017", "PASS", "asset-axis WRC coverage is complete")


def _missing(invariant_id: str, evidence: str) -> InvariantResult:
    return InvariantResult(invariant_id, "INCONCLUSIVE", f"missing evidence: {evidence}")
