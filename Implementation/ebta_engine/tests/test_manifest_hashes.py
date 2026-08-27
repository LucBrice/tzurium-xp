import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from shutil import copytree

from ebta_engine.manifests.hash_utils import sha256_file, sha256_tree
from ebta_engine.manifests.manifest_builder import build_manifest, verify_manifest
from ebta_engine.migrations.schema_migrations import migrate_reproducibility_manifest_1_0_to_2_0


ROOT = Path(__file__).resolve().parents[1]


class ManifestHashTests(unittest.TestCase):
    FIXED_TIME = datetime(2026, 7, 31, 12, 30, tzinfo=timezone.utc)

    def test_valid_fixture_content_checksum_matches_its_series(self):
        config = json.loads((ROOT / "fixtures" / "valid_minimal" / "config.json").read_text(encoding="utf-8"))
        expected = sha256_file(ROOT / "fixtures" / "valid_minimal" / "series" / "oos_primary_returns.json")
        self.assertEqual(config["data_snapshots"][0]["content_checksum"].upper(), expected)

    def test_manifest_detects_modified_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            manifest = build_manifest(
                package_dir,
                ["config.json", "registry.jsonl", "oos_access_log.jsonl", "reports/gates.json"],
                "PRE_OOS_SEALED",
            )
            self.assertEqual(verify_manifest(package_dir, manifest), [])
            (package_dir / "config.json").write_text(
                json.dumps({**json.loads((package_dir / "config.json").read_text()), "config_id": "MUTATED"}),
                encoding="utf-8",
            )
            self.assertIn("hash mismatch: config.json", verify_manifest(package_dir, manifest))

    def test_manifest_freeze_fields_are_deterministic_with_injected_clock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            first = build_manifest(package_dir, ["config.json"], "PRE_OOS_SEALED", clock=lambda: self.FIXED_TIME)
            second = build_manifest(package_dir, ["config.json"], "PRE_OOS_SEALED", clock=lambda: self.FIXED_TIME)
        self.assertEqual(first, second)
        self.assertRegex(first["code_hash"], r"^[0-9A-F]{64}$")
        self.assertRegex(first["data_hash"], r"^[0-9A-F]{64}$")
        self.assertEqual(first["timestamp"], "2026-07-31T12:30:00Z")
        self.assertEqual(first["timestamp_source"], "INJECTED_FIXTURE_CLOCK")

    def test_data_hash_changes_when_content_checksum_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            first = build_manifest(package_dir, ["config.json"], "PRE_OOS_SEALED", clock=lambda: self.FIXED_TIME)
            config_path = package_dir / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["data_snapshots"][0]["content_checksum"] = "A" * 64
            config_path.write_text(json.dumps(config), encoding="utf-8")
            second = build_manifest(package_dir, ["config.json"], "PRE_OOS_SEALED", clock=lambda: self.FIXED_TIME)
        self.assertNotEqual(first["data_hash"], second["data_hash"])
        self.assertEqual(first["code_hash"], second["code_hash"])

    def test_code_hash_changes_when_covered_code_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            code_root = Path(temp_dir) / "code"
            code_root.mkdir()
            source = code_root / "module.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            first = sha256_tree(code_root, relative_paths=["module.py"])
            source.write_text("VALUE = 2\n", encoding="utf-8")
            second = sha256_tree(code_root, relative_paths=["module.py"])
        self.assertNotEqual(first, second)

    def test_manifest_rejects_missing_content_checksum(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            config_path = package_dir / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            del config["data_snapshots"][0]["content_checksum"]
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing a non-empty content_checksum"):
                build_manifest(package_dir, ["config.json"], "PRE_OOS_SEALED")

    def test_manifest_rejects_malformed_content_checksum(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_dir = Path(temp_dir) / "package"
            copytree(ROOT / "fixtures" / "valid_minimal", package_dir)
            config_path = package_dir / "config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["data_snapshots"][0]["content_checksum"] = "not-a-real-checksum"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be a SHA-256 hex digest"):
                build_manifest(package_dir, ["config.json"], "PRE_OOS_SEALED")

    def test_tree_hash_rejects_empty_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "at least one file"):
                sha256_tree(Path(temp_dir), relative_paths=[])

    def test_manifest_rejects_naive_clock(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_manifest(
                ROOT / "fixtures" / "valid_minimal",
                ["config.json"],
                "PRE_OOS_SEALED",
                clock=lambda: datetime(2026, 7, 31, 12, 30),
            )

    def test_historical_manifest_migration_requires_explicit_evidence(self):
        with self.assertRaisesRegex(ValueError, "explicit non-empty FREEZE evidence"):
            migrate_reproducibility_manifest_1_0_to_2_0(
                {"schema_version": "1.0.0"},
                code_hash="",
                data_hash="DATA",
                timestamp="2026-07-31T12:30:00Z",
                timestamp_source="INJECTED_FIXTURE_CLOCK",
            )

    def test_historical_manifest_migration_rejects_malformed_evidence(self):
        with self.assertRaisesRegex(ValueError, "code_hash must be a SHA-256"):
            migrate_reproducibility_manifest_1_0_to_2_0(
                {"schema_version": "1.0.0"},
                code_hash="not-a-hash",
                data_hash="A" * 64,
                timestamp="2026-07-31T12:30:00Z",
                timestamp_source="INJECTED_FIXTURE_CLOCK",
            )


if __name__ == "__main__":
    unittest.main()
