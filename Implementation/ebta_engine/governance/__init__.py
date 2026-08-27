"""Governance controls derived from EBTA-DOC-1.1 SOP 13.

This package encodes machine-readable contracts for G-BIAS without creating a
normative source outside Protocole/.
"""

from .bias_registry import BIAS_RISKS, get_bias_risk, list_bias_risks
from .bias_gate import evaluate_bias_gate
from .candidate_family_checker import check_candidate_family
from .incident_logger import (
    DEFAULT_INCIDENT_LOG,
    IncidentLogNotFound,
    append_incident,
    load_incidents,
    load_open_incidents,
)
from .metric_lock_checker import check_metric_lock
from .oos_access_guard import guard_oos_access
from .preregistration_checker import check_preregistration_lock
from .registry_completeness_checker import check_registry_completeness
from .robustness_gate_checker import check_robustness_gate

__all__ = [
    "BIAS_RISKS",
    "DEFAULT_INCIDENT_LOG",
    "IncidentLogNotFound",
    "append_incident",
    "check_candidate_family",
    "check_metric_lock",
    "check_preregistration_lock",
    "check_registry_completeness",
    "check_robustness_gate",
    "evaluate_bias_gate",
    "get_bias_risk",
    "guard_oos_access",
    "list_bias_risks",
    "load_incidents",
    "load_open_incidents",
]
