import json
import tempfile
import unittest
from pathlib import Path
from shutil import copytree

from ebta_engine.manifests.manifest_builder import build_manifest
from ebta_engine.persistence import atomic_write_json
from ebta_engine.validators.package_validator import REQUIRED_PACKAGE_PATHS, validate_package_dir


ROOT = Path(__file__).resolve().parents[1]


class PackageValidatorTests(unittest.TestCase):
    def _valid_package(self, temp_dir: str) -> Path:
        package_dir = Path(temp_dir) / "package"
        copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
        return package_dir

    def _refresh_manifest(self, package_dir: Path) -> None:
        manifest = build_manifest(
            package_dir,
            sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json"),
            "VALIDATION_READY",
        )
        atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)

    def test_valid_minimal_package_validates_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            manifest = build_manifest(
                package_dir,
                sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json"),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            report = validate_package_dir(package_dir)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["gate_report"]["summary"]["inconclusive"], 0)
            self.assertTrue(all(result["status"] == "PASS" for result in report["invariant_results"]))

    def test_manifest_mismatch_fails_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            manifest = build_manifest(package_dir, ["config.json"], "PRE_OOS_SEALED")
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            config = json.loads((package_dir / "config.json").read_text(encoding="utf-8"))
            config["config_id"] = "MUTATED"
            atomic_write_json(package_dir / "config.json", config)
            report = validate_package_dir(package_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("hash mismatch: config.json", report["manifest_failures"])

    def test_gate_or_invariant_failure_fails_package_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            gates = json.loads((package_dir / "reports" / "gates.json").read_text(encoding="utf-8"))
            gates.pop("wrc_report")
            atomic_write_json(package_dir / "reports" / "gates.json", gates)
            manifest = build_manifest(
                package_dir,
                sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json"),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            report = validate_package_dir(package_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(report["gate_failures"])

    def test_missing_required_procedure_artifact_fails_package_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            (package_dir / "reports" / "search_space.json").unlink()
            manifest = build_manifest(
                package_dir,
                sorted(
                    path
                    for path in REQUIRED_PACKAGE_PATHS
                    if path not in {"manifests/reproducibility_manifest.json", "reports/search_space.json"}
                ),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            report = validate_package_dir(package_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("reports/search_space.json", report["missing_paths"])

    def test_missing_incubation_gate_report_fails_package_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            (package_dir / "reports" / "incubation_gate.json").unlink()
            manifest = build_manifest(
                package_dir,
                sorted(
                    path
                    for path in REQUIRED_PACKAGE_PATHS
                    if path not in {"manifests/reproducibility_manifest.json", "reports/incubation_gate.json"}
                ),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            report = validate_package_dir(package_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("reports/incubation_gate.json", report["missing_paths"])

    def test_failed_incubation_gate_report_fails_package_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            atomic_write_json(
                package_dir / "reports" / "incubation_gate.json",
                {"artifact_type": "incubation_gate", "status": "FAIL", "failures": ["statistical_status"]},
            )
            manifest = build_manifest(
                package_dir,
                sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json"),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            report = validate_package_dir(package_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("incubation_gate status is FAIL", report["semantic_errors"])

    def test_failed_economic_global_status_fails_package_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            economic = json.loads((package_dir / "reports" / "economic.json").read_text(encoding="utf-8"))
            economic["global_status"] = "FAIL"
            atomic_write_json(package_dir / "reports" / "economic.json", economic)
            manifest = build_manifest(
                package_dir,
                sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json"),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            report = validate_package_dir(package_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("economic global_status is FAIL", report["semantic_errors"])

    def test_rejected_economic_global_status_fails_package_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            economic = json.loads((package_dir / "reports" / "economic.json").read_text(encoding="utf-8"))
            economic["global_status"] = "REJECTED_ECONOMIC"
            atomic_write_json(package_dir / "reports" / "economic.json", economic)
            manifest = build_manifest(
                package_dir,
                sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json"),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            report = validate_package_dir(package_dir)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn("economic global_status is REJECTED_ECONOMIC", report["semantic_errors"])

    def test_persisted_gate_verdict_divergences_are_named_and_blocking(self):
        mutations = {
            "statistical": "FAIL",
            "economic": "REJECTED_ECONOMIC",
            "final": "INCONCLUSIVE",
        }
        for field, divergent_value in mutations.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp_dir:
                package_dir = self._valid_package(temp_dir)
                economic_path = package_dir / "reports" / "economic.json"
                economic = json.loads(economic_path.read_text(encoding="utf-8"))
                economic.update(
                    {
                        "statistical_status": "PASS",
                        "economic_status": "PASS",
                        "global_status": "PASS",
                    }
                )
                atomic_write_json(economic_path, economic)
                evidence_path = package_dir / "reports" / "invariant_evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                evidence["gate_reports"][field] = divergent_value
                atomic_write_json(evidence_path, evidence)
                self._refresh_manifest(package_dir)

                report = validate_package_dir(package_dir)

                self.assertEqual(report["status"], "FAIL")
                self.assertTrue(
                    any(
                        f"invariant_evidence.gate_reports.{field}" in error
                        for error in report["semantic_errors"]
                    )
                )

    def test_wrc_and_economic_statistical_divergence_is_named_and_blocking(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = self._valid_package(temp_dir)
            economic_path = package_dir / "reports" / "economic.json"
            economic = json.loads(economic_path.read_text(encoding="utf-8"))
            economic["statistical_status"] = "FAIL"
            atomic_write_json(economic_path, economic)
            self._refresh_manifest(package_dir)

            report = validate_package_dir(package_dir)

            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any(
                    "wrc.verdict='PASS' economic.statistical_status='FAIL'" in error
                    for error in report["semantic_errors"]
                )
            )

    def test_present_g_bias_report_must_pass_when_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            manifest = build_manifest(
                package_dir,
                sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json"),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)
            atomic_write_json(package_dir / "reports" / "g_bias.json", {"artifact_type": "g_bias_report", "status": "FAIL"})

            report = validate_package_dir(package_dir)

            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["bias_gate_failures"], ["G-BIAS FAIL"])

    def test_enforced_g_bias_report_missing_fails_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            manifest = build_manifest(
                package_dir,
                sorted(path for path in REQUIRED_PACKAGE_PATHS if path != "manifests/reproducibility_manifest.json"),
                "VALIDATION_READY",
            )
            atomic_write_json(package_dir / "manifests" / "reproducibility_manifest.json", manifest)

            report = validate_package_dir(package_dir, enforce_bias_governance=True)

            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["bias_gate_failures"], ["missing optional enforced artifact: reports/g_bias.json"])


if __name__ == "__main__":
    unittest.main()
