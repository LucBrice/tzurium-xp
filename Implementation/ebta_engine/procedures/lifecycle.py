"""Incubation, deployment, and lifecycle stage checks.

Source: SOP 11 sections 3, 13, 15, 20, 28, and 38; SOP 12 sections 3 and 38;
DN-035 to DN-041.
Type: IMPLEMENTATION_DETAIL.
"""

from __future__ import annotations

from typing import Any


def incubation_gate(evidence: dict[str, Any]) -> dict[str, Any]:
    required = {
        "statistical_status": "PASS",
        "economic_status": "PASS",
        "robustness_status": "PASS",
        "execution_status": "PASS",
        "package_stage": "VALIDATION_READY",
        "reproduction_status": "PASS",
    }
    failures = [key for key, expected in required.items() if evidence.get(key) != expected]
    return {
        "artifact_type": "incubation_gate",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }


def deployment_gate(evidence: dict[str, Any]) -> dict[str, Any]:
    required = {
        "paper_trading_status": "PASS",
        "package_stage": "DEPLOYMENT_CERTIFIED",
        "kill_switch_tested": True,
        "live_deployment_status": "PASS",
        "live_approval_status": "PASS",
    }
    failures = [key for key, expected in required.items() if evidence.get(key) != expected]
    return {
        "artifact_type": "deployment_gate",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }
