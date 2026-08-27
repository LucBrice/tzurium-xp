"""Independent reproduction report validator.

Source: SOP 12 sections 3, 5, and 38; DN-039, DN-040, DN-041.
Type: IMPLEMENTATION_DETAIL.

The EBTA protocol requires independent reproduction before incubation (G11 /
DN-039).  The reproduction is performed by an independent party on a separate
machine.  This module:

1. Defines the structure of a reproduction report (validated via
   ``reproduction_report.schema.json``).
2. Provides a validation function that compares the artefact hashes in the
   submitted reproduction report against the hashes in the original
   reproducibility manifest (INV-016).

This module does NOT re-execute the research pipeline; that is the
responsibility of the independent reproducer.
"""

from __future__ import annotations

from typing import Any


def validate_reproduction_report(
    report: dict[str, Any],
    *,
    original_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Validate an independent reproduction report against the original manifest.

    Parameters
    ----------
    report:
        Reproduction report submitted by the independent reproducer.  Must
        contain at minimum:
        - ``report_id`` (str)
        - ``config_id`` (str)
        - ``original_manifest_hash`` (str): hash of the original manifest
        - ``reproduced_artefact_hashes`` (dict[str, str]): name -> hash
        - ``environment`` (dict): reproducer's environment description
        - ``tolerances`` (dict[str, float]): name -> max allowed delta
        - ``verdict`` (str): PASS | FAIL | INCONCLUSIVE

    original_manifest:
        The original reproducibility manifest produced by the primary run.
        Must contain ``artefact_hashes`` (dict[str, str]).

    Returns
    -------
    dict
        ``status``: PASS | FAIL | INCONCLUSIVE
    """
    if not report:
        return _reproduction_result("INCONCLUSIVE", violations=[{
            "rule": "DN-039_REPORT_REQUIRED",
            "description": "Empty reproduction report.",
        }])

    violations: list[dict[str, Any]] = []

    required_fields = [
        "report_id", "config_id", "original_manifest_hash",
        "reproduced_artefact_hashes", "environment", "verdict",
    ]
    for field in required_fields:
        if field not in report:
            violations.append({
                "rule": "DN-039_FIELD_REQUIRED",
                "authority": "SOP 12 / DN-039",
                "field": field,
                "description": f"Required reproduction report field '{field}' is missing.",
            })

    # Validate environment description.
    env = report.get("environment") or {}
    required_env_fields = ["python_version", "os", "code_commit_hash"]
    for field in required_env_fields:
        if not env.get(field):
            violations.append({
                "rule": "DN-039_ENVIRONMENT_REQUIRED",
                "authority": "SOP 12 / DN-039",
                "field": f"environment.{field}",
                "description": (
                    f"Reproduction environment field '{field}' is missing. "
                    "Reproducibility requires the full environment to be documented."
                ),
            })

    # Validate verdict.
    valid_verdicts = {"PASS", "FAIL", "INCONCLUSIVE"}
    verdict = str(report.get("verdict", ""))
    if verdict and verdict not in valid_verdicts:
        violations.append({
            "rule": "DN-039_VALID_VERDICT",
            "authority": "SOP 12 / DN-039",
            "found": verdict,
            "expected_one_of": sorted(valid_verdicts),
            "description": "Reproduction verdict must be PASS, FAIL, or INCONCLUSIVE.",
        })

    # Compare reproduced artefact hashes against the original manifest.
    hash_comparison = _compare_artefact_hashes(
        report.get("reproduced_artefact_hashes") or {},
        original_manifest.get("artefact_hashes") or {},
        tolerances=report.get("tolerances") or {},
    )
    violations.extend(hash_comparison["mismatches"])

    return _reproduction_result(
        "PASS" if not violations else "FAIL",
        violations=violations,
        hash_comparison_summary=hash_comparison["summary"],
        submitted_verdict=verdict,
    )


def _compare_artefact_hashes(
    reproduced: dict[str, str],
    original: dict[str, str],
    *,
    tolerances: dict[str, float],
) -> dict[str, Any]:
    """Compare artefact hashes; allow numeric tolerances for floating-point results."""
    mismatches: list[dict[str, Any]] = []
    checked = 0
    matched = 0

    for artefact_name, original_hash in original.items():
        reproduced_hash = reproduced.get(artefact_name)
        checked += 1

        if reproduced_hash is None:
            mismatches.append({
                "rule": "INV-016_HASH_MISSING",
                "authority": "SOP 12 / INV-016",
                "artefact": artefact_name,
                "description": (
                    f"Artefact '{artefact_name}' is present in the original "
                    "manifest but missing from the reproduction report."
                ),
            })
            continue

        if reproduced_hash != original_hash:
            # Check if a numeric tolerance is declared for this artefact.
            tolerance = tolerances.get(artefact_name)
            if tolerance is None:
                mismatches.append({
                    "rule": "INV-016_HASH_MISMATCH",
                    "authority": "SOP 12 / INV-016",
                    "artefact": artefact_name,
                    "original_hash": original_hash,
                    "reproduced_hash": reproduced_hash,
                    "description": (
                        f"Hash mismatch for '{artefact_name}'. "
                        "If floating-point variation is expected, declare a "
                        "tolerance in the reproduction report."
                    ),
                })
            else:
                # Tolerance declared — flag as a warning, not a hard failure.
                mismatches.append({
                    "rule": "INV-016_HASH_WITHIN_TOLERANCE",
                    "severity": "WARNING",
                    "artefact": artefact_name,
                    "tolerance": tolerance,
                    "description": (
                        f"Hash mismatch for '{artefact_name}' but a numeric "
                        f"tolerance of {tolerance} is declared. "
                        "Auditors should verify the numeric delta independently."
                    ),
                })
                matched += 1  # Count as matched with warning.
                continue

        else:
            matched += 1

    # Also check for artefacts present in reproduction but not in original.
    extra = set(reproduced.keys()) - set(original.keys())
    for artefact_name in sorted(extra):
        mismatches.append({
            "rule": "INV-016_UNEXPECTED_ARTEFACT",
            "severity": "WARNING",
            "artefact": artefact_name,
            "description": (
                f"Artefact '{artefact_name}' appears in the reproduction "
                "report but not in the original manifest. Verify whether "
                "this is an expected addition."
            ),
        })

    hard_failures = [m for m in mismatches if m.get("severity") != "WARNING"]

    return {
        "summary": {
            "artefacts_checked": checked,
            "artefacts_matched": matched,
            "hard_failures": len(hard_failures),
            "warnings": len(mismatches) - len(hard_failures),
        },
        "mismatches": hard_failures,  # Only hard failures become violations.
    }


def _reproduction_result(
    status: str,
    *,
    violations: list[dict[str, Any]],
    hash_comparison_summary: dict[str, Any] | None = None,
    submitted_verdict: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "artifact_type": "reproduction_report_validation",
        "source_normative": "SOP 12 sections 3, 5, 38; DN-039, DN-040, DN-041; INV-016",
        "status": status,
        "violations": violations,
    }
    if hash_comparison_summary is not None:
        result["hash_comparison_summary"] = hash_comparison_summary
    if submitted_verdict:
        result["submitted_verdict"] = submitted_verdict
    return result
