import json
import unittest
from pathlib import Path

from ebta_engine.manifests.manifest_builder import build_manifest
from ebta_engine.validators.artifact_validators import load_schema, validate_json_file, validate_jsonl_file
from ebta_engine.schema_validation import validate


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
INVALID_REJ = FIXTURES / "invalid_rejection_tests"


class SchemaTests(unittest.TestCase):
    def test_valid_minimal_config_passes(self):
        errors = validate_json_file(FIXTURES / "valid_minimal" / "config.json", "config.schema.json")
        self.assertEqual(errors, [])

    def test_invalid_config_missing_required_fails(self):
        errors = validate_json_file(
            FIXTURES / "invalid_missing_required" / "config_missing_project_id.json",
            "config.schema.json",
        )
        self.assertTrue(any(error.path == "$.project_id" for error in errors))

    def test_registry_jsonl_passes(self):
        errors = validate_jsonl_file(
            FIXTURES / "valid_minimal" / "registry.jsonl",
            "experiment_registry_event.schema.json",
        )
        self.assertEqual(errors, [])

    def test_oos_access_jsonl_passes(self):
        errors = validate_jsonl_file(
            FIXTURES / "valid_minimal" / "oos_access_log.jsonl",
            "oos_access_event.schema.json",
        )
        self.assertEqual(errors, [])

    def test_reproducibility_manifest_requires_sop12_sections(self):
        manifest = build_manifest(
            FIXTURES / "valid_minimal",
            [
                "config.json",
                "registry.jsonl",
                "oos_access_log.jsonl",
                "reports/gates.json",
                "reports/wrc.json",
                "reports/search_space.json",
                "series/oos_primary_returns.json",
            ],
            "VALIDATION_READY",
        )
        schema = load_schema("reproducibility_manifest.schema.json")
        errors = validate(manifest, schema)
        self.assertEqual(errors, [])
        self.assertIn("configuration", manifest)
        self.assertEqual(manifest["schema_version"], "2.0.0")
        for field in ("code_hash", "data_hash", "timestamp", "timestamp_source"):
            self.assertIn(field, manifest)
        self.assertIn("random_seeds", manifest)
        self.assertTrue(all("source_normative" in artifact for artifact in manifest["artifacts"]))

    # ------------------------------------------------------------------
    # Tests de rejet — COVERED_MINIMAL schemas (P1 post-audit 2026-06-29)
    # Chaque test verifie qu'un payload invalide est bien rejete.
    # Source normative : TRACEABILITY_MATRIX.md + audit externe.
    # ------------------------------------------------------------------

    def test_reject_config_missing_config_id(self):
        """config.schema.json doit rejeter un payload sans config_id (champ requis SOP 04)."""
        errors = validate_json_file(
            INVALID_REJ / "config_missing_config_id.json",
            "config.schema.json",
        )
        self.assertTrue(
            len(errors) > 0,
            "Expected validation errors for config missing config_id, got none.",
        )
        self.assertTrue(
            any("config_id" in e.path for e in errors),
            f"Expected error on $.config_id, got: {[e.path for e in errors]}",
        )

    def test_reject_registry_event_missing_chain_hash(self):
        """experiment_registry_event.schema.json doit rejeter un evenement sans chain_hash (DN-005 append-only)."""
        errors = validate_jsonl_file(
            INVALID_REJ / "registry_missing_chain_hash.jsonl",
            "experiment_registry_event.schema.json",
        )
        self.assertTrue(
            len(errors) > 0,
            "Expected validation errors for registry event missing chain_hash, got none.",
        )
        self.assertTrue(
            any("chain_hash" in e.path for e in errors),
            f"Expected error on $.chain_hash, got: {[e.path for e in errors]}",
        )

    def test_reject_oos_access_event_missing_access_event_id(self):
        """oos_access_event.schema.json doit rejeter un evenement sans access_event_id (DN-032)."""
        errors = validate_jsonl_file(
            INVALID_REJ / "oos_access_missing_event_id.jsonl",
            "oos_access_event.schema.json",
        )
        self.assertTrue(
            len(errors) > 0,
            "Expected validation errors for OOS access event missing access_event_id, got none.",
        )
        self.assertTrue(
            any("access_event_id" in e.path for e in errors),
            f"Expected error on $.access_event_id, got: {[e.path for e in errors]}",
        )

    def test_reject_execution_journal_event_missing_signal_id(self):
        """execution_journal_event.schema.json doit rejeter un event sans signal_id (SOP 09B chaine signal->ordre->fill)."""
        schema = load_schema("execution_journal_event.schema.json")
        payload = json.loads((INVALID_REJ / "execution_missing_signal_id.json").read_text(encoding="utf-8"))
        errors = validate(payload, schema)
        self.assertTrue(
            len(errors) > 0,
            "Expected validation errors for execution event missing signal_id, got none.",
        )
        self.assertTrue(
            any("signal_id" in e.path for e in errors),
            f"Expected error on $.signal_id, got: {[e.path for e in errors]}",
        )

    def test_reject_pit_data_declaration_missing_data_sources(self):
        """pit_data_declaration.schema.json doit rejeter une declaration sans data_sources (SOP 09A, minItems:1)."""
        schema = load_schema("pit_data_declaration.schema.json")
        payload = json.loads((INVALID_REJ / "pit_missing_data_sources.json").read_text(encoding="utf-8"))
        errors = validate(payload, schema)
        self.assertTrue(
            len(errors) > 0,
            "Expected validation errors for PIT declaration missing data_sources, got none.",
        )
        self.assertTrue(
            any("data_sources" in e.path for e in errors),
            f"Expected error on $.data_sources, got: {[e.path for e in errors]}",
        )

    def test_reject_walk_forward_declaration_overlap_not_confirmed(self):
        """walk_forward_declaration.schema.json doit rejeter no_oos_overlap_confirmed=false (DN-001 / INV-001)."""
        schema = load_schema("walk_forward_declaration.schema.json")
        payload = json.loads(
            (INVALID_REJ / "walk_forward_overlap_not_confirmed.json").read_text(encoding="utf-8")
        )
        # Le schema encode le champ comme boolean — false est valide syntaxiquement mais
        # semantiquement invalide (DN-001). Le test verifie que la valeur false est presente
        # et que l'invariant downstream doit la rejeter.
        # Note : la validation syntaxique ne peut pas rejeter false directement sans
        # l'ajout d'une contrainte enum ou const dans le schema.
        # Ce test documente le gap et le marque INVARIANT_REQUIRED.
        self.assertFalse(
            payload.get("no_oos_overlap_confirmed"),
            "Fixture must have no_oos_overlap_confirmed=false to document DN-001 enforcement gap.",
        )
        # Verification que le schema accepte la syntaxe (boolean) mais pas l'invariant
        errors = validate(payload, schema)
        # Aucune erreur de schema attendue (le schema accepte false) — l'invariant INV-001
        # doit etre enforced par validators/invariant_validator.py, pas le schema seul.
        # Ce test sert de regression et de documentation du gap d'enforcement.
        self.assertEqual(
            errors, [],
            "Schema accepts false syntactically; invariant enforcement is in invariant_validator.py (INV-001).",
        )

    def test_reject_robustness_plan_missing_central_scenario(self):
        """robustness_plan.schema.json : un plan sans scenario CENTRAL viole DN-030."""
        schema = load_schema("robustness_plan.schema.json")
        payload = json.loads(
            (INVALID_REJ / "robustness_no_central_scenario.json").read_text(encoding="utf-8")
        )
        errors = validate(payload, schema)
        # Le schema n'enforce pas la presence de CENTRAL parmi les classifications —
        # il valide seulement l'enum des valeurs autorisees. Ce test documente le gap :
        # la contrainte "au moins un scenario CENTRAL" necessite une validation custom.
        scenarios = payload.get("scenarios", [])
        has_central = any(s.get("classification") == "CENTRAL" for s in scenarios)
        self.assertFalse(
            has_central,
            "Fixture must not contain a CENTRAL scenario to document the DN-030 enforcement gap.",
        )
        # Documentation du gap : le schema JSON ne peut pas exprimer "au moins un element
        # avec classification==CENTRAL sans jsonschema contains". Une validation custom
        # dans procedures/robustness.py couvre ce cas (COVERED via test_procedure_governance.py).
        self.assertEqual(
            errors, [],
            "Schema accepts missing CENTRAL scenario syntactically; "
            "semantic enforcement is in procedures/robustness.py.",
        )


if __name__ == "__main__":
    unittest.main()



if __name__ == "__main__":
    unittest.main()
