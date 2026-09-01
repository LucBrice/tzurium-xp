from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


def _find_repo_root(script_path: Path) -> Path:
    """Find the checkout root for either the private or mirrored layout."""
    for candidate in script_path.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError(f"Cannot locate repository root from {script_path}")


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
TOOLS_ROOT = REPO_ROOT / ".ai" / "tools"
if not TOOLS_ROOT.is_dir():
    TOOLS_ROOT = REPO_ROOT / "verification"
VERIFY_PATH = TOOLS_ROOT / "verify_local.py"
HARNESS_PATH = TOOLS_ROOT / "tests" / "test_workflow_state_machine.ps1"
WORKFLOW_STATE_PATH = TOOLS_ROOT / "workflow_state.ps1"


def _load_verify_local():
    spec = importlib.util.spec_from_file_location("verify_local_under_test", VERIFY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_local = _load_verify_local()


class _Completed:
    def __init__(self, returncode: int):
        self.returncode = returncode


class VerifyLocalContractTests(unittest.TestCase):
    def test_manifest_preserves_reviewed_scopes_and_permanent_architecture_mode(self) -> None:
        commands = [" ".join(step.command_template) for step in verify_local.STEP_SPECS]
        joined = "\n".join(commands)
        if not verify_local.PRIVATE_TOOLS_LAYOUT:
            self.assertEqual(
                [step.name for step in verify_local.STEP_SPECS],
                [
                    "public_pyrefly",
                    "public_ruff",
                    "canonical_unittest",
                    "public_verify_local_unittest",
                ],
            )
            self.assertIn("-m pyrefly check Implementation/ebta_engine", joined)
            self.assertIn("-m ruff check Implementation/ebta_engine", joined)
            self.assertIn(
                "-m unittest discover -s verification/tests -p test_verify_local.py",
                joined,
            )
            self.assertNotIn(".ai/tools", joined)
            self.assertNotIn("Implementation/ebta_private", joined)
            return
        self.assertIn(
            '--replace-imports-with-any nautilus_trader.* '
            "Implementation/ebta_engine Implementation/ebta_private Implementation/notebooks",
            joined,
        )
        self.assertIn(
            "-m ruff check Implementation/ebta_engine Implementation/ebta_private",
            joined,
        )
        self.assertIn(
            "-m pyrefly check --python-interpreter-path python "
            ".ai/tools/session_trace.py .ai/tools/tests/test_session_trace.py",
            joined,
        )
        self.assertIn(
            "-m ruff check .ai/tools/session_trace.py .ai/tools/tests/test_session_trace.py",
            joined,
        )
        self.assertIn(
            "-m pyrefly check --python-interpreter-path python "
            ".ai/tools/session_proof.py .ai/tools/tests/test_session_proof.py",
            joined,
        )
        self.assertIn(
            "-m ruff check .ai/tools/session_proof.py .ai/tools/tests/test_session_proof.py",
            joined,
        )
        self.assertIn(
            "-m pyrefly check --python-interpreter-path python "
            ".ai/tools/plan_conformance.py .ai/tools/tests/test_plan_conformance.py",
            joined,
        )
        self.assertIn(
            "-m ruff check .ai/tools/plan_conformance.py .ai/tools/tests/test_plan_conformance.py",
            joined,
        )
        self.assertIn(
            "-m pyrefly check --python-interpreter-path python "
            ".ai/tools/bootstrap_public_engine.py .ai/tools/tests/test_bootstrap_public_engine.py",
            joined,
        )
        self.assertIn(
            "-m ruff check .ai/tools/bootstrap_public_engine.py "
            ".ai/tools/tests/test_bootstrap_public_engine.py",
            joined,
        )
        self.assertIn(
            "-m unittest discover -s Implementation/ebta_engine/tests -t Implementation",
            joined,
        )
        self.assertIn(
            "-m unittest discover -s Implementation/ebta_private/tests -t Implementation",
            joined,
        )
        self.assertIn("test_workflow_state_machine.ps1", joined)
        self.assertIn(
            "-m unittest discover -s .ai/tools/tests -p test_session_trace.py",
            joined,
        )
        self.assertIn(
            "-m unittest discover -s .ai/tools/tests -p test_session_proof.py",
            joined,
        )
        self.assertIn(
            "-m unittest discover -s .ai/tools/tests -p test_verify_local.py",
            joined,
        )
        self.assertIn(
            "-m unittest discover -s .ai/tools/tests -p test_plan_conformance.py",
            joined,
        )
        self.assertIn(
            "-m unittest discover -s .ai/tools/tests -p test_bootstrap_public_engine.py",
            joined,
        )
        self.assertIn("--validate .ai/architecture/architecture.json", joined)
        self.assertIn(
            "--schema .ai/checkpoint.json .ai/checkpoint.schema.json",
            joined,
        )
        self.assertIn(
            "--schema Implementation/Active/tracking.json Implementation/Active/tracking.schema.json",
            joined,
        )
        self.assertNotIn("--check-initial", joined)

    def test_every_step_runs_and_one_failure_keeps_global_verdict_nonzero(self) -> None:
        calls: list[tuple[str, ...]] = []
        codes = iter([0, 1] + [0] * (len(verify_local.STEP_SPECS) - 2))

        def runner(command, **_kwargs):
            calls.append(tuple(command))
            return _Completed(next(codes))

        output = io.StringIO()
        result = verify_local.run_verifications(
            runner=runner,
            python_executable="python-test",
            powershell_executable="pwsh-test",
            stream=output,
        )
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), len(verify_local.STEP_SPECS))
        self.assertIn("ruff: FAIL", output.getvalue())
        self.assertIn("VERDICT: FAIL", output.getvalue())
        self.assertNotIn("VERDICT: PASS", output.getvalue())

    def test_missing_powershell_is_fail_closed_but_later_steps_still_run(self) -> None:
        calls: list[tuple[str, ...]] = []

        def runner(command, **_kwargs):
            calls.append(tuple(command))
            return _Completed(0)

        output = io.StringIO()
        result = verify_local.run_verifications(
            runner=runner,
            python_executable="python-test",
            powershell_executable=None,
            stream=output,
        )
        if not verify_local.PRIVATE_TOOLS_LAYOUT:
            self.assertEqual(result, 0)
            self.assertEqual(len(calls), len(verify_local.STEP_SPECS))
            self.assertNotIn("FAIL", output.getvalue())
            return
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), len(verify_local.STEP_SPECS) - 1)
        self.assertIn("workflow_state_machine: FAIL", output.getvalue())
        self.assertIn("architecture: PASS", output.getvalue())

    @unittest.skipUnless(
        HARNESS_PATH.is_file() and WORKFLOW_STATE_PATH.is_file(),
        "workflow-state harness is private-only",
    )
    def test_real_workflow_state_regression_makes_harness_red(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if powershell is None:
            self.fail("PowerShell host missing: hostile workflow proof cannot run")

        with tempfile.TemporaryDirectory(prefix="ebta_workflow_regression_") as temp_dir:
            regressed = Path(temp_dir) / "workflow_state_regressed.ps1"
            regressed.write_text(
                WORKFLOW_STATE_PATH.read_text(encoding="utf-8")
                + "\nfunction Move-WorkflowStage { param($Contract, $State, $Action) }\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(HARNESS_PATH),
                    "-WorkflowStateScript",
                    str(regressed),
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
