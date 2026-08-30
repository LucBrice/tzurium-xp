import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def normalized_text(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class RepositoryEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.readme = normalized_text(REPOSITORY_ROOT / "README.md")
        cls.workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ebta-engine-ci.yml").read_text(
            encoding="utf-8"
        )

    def test_readme_identifies_mirror_and_private_editing_authority(self):
        self.assertIn("generated public mirror", self.readme)
        self.assertIn("editable sources are governed in the private EBTA repository", self.readme)
        self.assertIn("neither this repository nor one of its paths is an editing authority", self.readme)

    def test_readme_does_not_restore_canonical_editable_source_claim(self):
        self.assertNotIn("canonical editable source", self.readme)
        self.assertNotIn("canonical public source", self.readme)

    def test_git_installation_guidance_is_external_and_immutable(self):
        self.assertIn("External consumers that install from Git", self.readme)
        self.assertIn("pin a verified full commit SHA", self.readme)
        self.assertRegex(
            self.readme,
            re.escape("git+https://github.com/LucBrice/tzurium-xp.git@<full-commit-sha>"),
        )
        self.assertIn("private EBTA repository does not consume this mirror through that VCS pin", self.readme)

    def test_export_report_is_described_as_historical_not_live(self):
        self.assertIn("historical attestation of the initial allowlisted snapshot", self.readme)
        self.assertIn("It is not a live manifest of the current mirror", self.readme)
        self.assertIn("Current candidates are composed from a closed manifest", self.readme)
        self.assertTrue((REPOSITORY_ROOT / "public_export_report.json").is_file())

    def test_public_ci_retains_mirror_identity_and_pull_request_boundary(self):
        self.assertIn("CI autonome du miroir public genere TZURIUM XP", self.workflow)
        self.assertNotIn("CI autonome de la source canonique publique TZURIUM XP", self.workflow)
        self.assertRegex(self.workflow, r"(?m)^  pull_request:\s*$")


if __name__ == "__main__":
    unittest.main()
