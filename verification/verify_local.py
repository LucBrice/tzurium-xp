#!/usr/bin/env python
"""Run the complete EBTA local/CI verification contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TextIO


SCRIPT_PATH = Path(__file__).resolve()


def _find_repo_root(script_path: Path) -> Path:
    """Find the checkout root for either the private or mirrored layout."""
    for candidate in script_path.parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError(f"Cannot locate repository root from {script_path}")


REPO_ROOT = _find_repo_root(SCRIPT_PATH)
PRIVATE_TOOLS_LAYOUT = (REPO_ROOT / ".ai" / "tools").is_dir()
PYTHON_TOKEN = "{python}"
POWERSHELL_TOKEN = "{powershell}"
SCRIPT_TOKEN = "{script}"
AUTO_POWERSHELL = "{auto-powershell}"


class StepSpec:
    __slots__ = ("command_template", "name")

    def __init__(self, name: str, command_template: tuple[str, ...]) -> None:
        self.name = name
        self.command_template = command_template


PRIVATE_STEP_SPECS = (
    StepSpec(
        "pyrefly",
        (
            PYTHON_TOKEN,
            "-m",
            "pyrefly",
            "check",
            "--python-interpreter-path",
            "python",
            "--replace-imports-with-any",
            "nautilus_trader.*",
            "Implementation/ebta_engine",
            "Implementation/ebta_private",
            "Implementation/notebooks",
        ),
    ),
    StepSpec(
        "ruff",
        (
            PYTHON_TOKEN,
            "-m",
            "ruff",
            "check",
            "Implementation/ebta_engine",
            "Implementation/ebta_private",
        ),
    ),
    StepSpec(
        "session_trace_pyrefly",
        (
            PYTHON_TOKEN,
            "-m",
            "pyrefly",
            "check",
            "--python-interpreter-path",
            "python",
            ".ai/tools/session_trace.py",
            ".ai/tools/tests/test_session_trace.py",
        ),
    ),
    StepSpec(
        "session_trace_ruff",
        (
            PYTHON_TOKEN,
            "-m",
            "ruff",
            "check",
            ".ai/tools/session_trace.py",
            ".ai/tools/tests/test_session_trace.py",
        ),
    ),
    StepSpec(
        "session_proof_pyrefly",
        (
            PYTHON_TOKEN,
            "-m",
            "pyrefly",
            "check",
            "--python-interpreter-path",
            "python",
            ".ai/tools/session_proof.py",
            ".ai/tools/tests/test_session_proof.py",
        ),
    ),
    StepSpec(
        "session_proof_ruff",
        (
            PYTHON_TOKEN,
            "-m",
            "ruff",
            "check",
            ".ai/tools/session_proof.py",
            ".ai/tools/tests/test_session_proof.py",
        ),
    ),
    StepSpec(
        "plan_conformance_pyrefly",
        (
            PYTHON_TOKEN,
            "-m",
            "pyrefly",
            "check",
            "--python-interpreter-path",
            "python",
            ".ai/tools/plan_conformance.py",
            ".ai/tools/tests/test_plan_conformance.py",
        ),
    ),
    StepSpec(
        "plan_conformance_ruff",
        (
            PYTHON_TOKEN,
            "-m",
            "ruff",
            "check",
            ".ai/tools/plan_conformance.py",
            ".ai/tools/tests/test_plan_conformance.py",
        ),
    ),
    StepSpec(
        "bootstrap_public_engine_pyrefly",
        (
            PYTHON_TOKEN,
            "-m",
            "pyrefly",
            "check",
            "--python-interpreter-path",
            "python",
            ".ai/tools/bootstrap_public_engine.py",
            ".ai/tools/tests/test_bootstrap_public_engine.py",
        ),
    ),
    StepSpec(
        "bootstrap_public_engine_ruff",
        (
            PYTHON_TOKEN,
            "-m",
            "ruff",
            "check",
            ".ai/tools/bootstrap_public_engine.py",
            ".ai/tools/tests/test_bootstrap_public_engine.py",
        ),
    ),
    StepSpec(
        "canonical_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            "Implementation/ebta_engine/tests",
            "-t",
            "Implementation",
        ),
    ),
    StepSpec(
        "private_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            "Implementation/ebta_private/tests",
            "-t",
            "Implementation",
        ),
    ),
    StepSpec(
        "checkpoint_schema",
        (
            PYTHON_TOKEN,
            SCRIPT_TOKEN,
            "--schema",
            ".ai/checkpoint.json",
            ".ai/checkpoint.schema.json",
        ),
    ),
    StepSpec(
        "tracking_schema",
        (
            PYTHON_TOKEN,
            SCRIPT_TOKEN,
            "--schema",
            "Implementation/Active/tracking.json",
            "Implementation/Active/tracking.schema.json",
        ),
    ),
    StepSpec(
        "workflow_state_machine",
        (
            POWERSHELL_TOKEN,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ".ai/tools/tests/test_workflow_state_machine.ps1",
        ),
    ),
    StepSpec(
        "session_trace_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".ai/tools/tests",
            "-p",
            "test_session_trace.py",
        ),
    ),
    StepSpec(
        "session_proof_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".ai/tools/tests",
            "-p",
            "test_session_proof.py",
        ),
    ),
    StepSpec(
        "plan_conformance_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".ai/tools/tests",
            "-p",
            "test_plan_conformance.py",
        ),
    ),
    StepSpec(
        "bootstrap_public_engine_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".ai/tools/tests",
            "-p",
            "test_bootstrap_public_engine.py",
        ),
    ),
    StepSpec(
        "test_verify_local_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".ai/tools/tests",
            "-p",
            "test_verify_local.py",
        ),
    ),
    StepSpec(
        "sync_engine_mirror_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".ai/tools/tests",
            "-p",
            "test_sync_engine_mirror.py",
        ),
    ),
    StepSpec(
        "architecture",
        (
            PYTHON_TOKEN,
            ".ai/architecture/extract_drawio_architecture.py",
            "--validate",
            ".ai/architecture/architecture.json",
        ),
    ),
)

PUBLIC_STEP_SPECS = (
    StepSpec(
        "public_pyrefly",
        (
            PYTHON_TOKEN,
            "-m",
            "pyrefly",
            "check",
            "Implementation/ebta_engine",
        ),
    ),
    StepSpec(
        "public_ruff",
        (
            PYTHON_TOKEN,
            "-m",
            "ruff",
            "check",
            "Implementation/ebta_engine",
        ),
    ),
    StepSpec(
        "canonical_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            "Implementation/ebta_engine/tests",
            "-t",
            "Implementation",
        ),
    ),
    StepSpec(
        "public_verify_local_unittest",
        (
            PYTHON_TOKEN,
            "-m",
            "unittest",
            "discover",
            "-s",
            "verification/tests",
            "-p",
            "test_verify_local.py",
        ),
    ),
)

STEP_SPECS = PRIVATE_STEP_SPECS if PRIVATE_TOOLS_LAYOUT else PUBLIC_STEP_SPECS


def _resolve_command(
    spec: StepSpec,
    *,
    python_executable: str,
    powershell_executable: str | None,
) -> tuple[str, ...] | None:
    resolved: list[str] = []
    for item in spec.command_template:
        if item == PYTHON_TOKEN:
            resolved.append(python_executable)
        elif item == SCRIPT_TOKEN:
            resolved.append(str(SCRIPT_PATH))
        elif item == POWERSHELL_TOKEN:
            if powershell_executable is None:
                return None
            resolved.append(powershell_executable)
        else:
            resolved.append(item)
    return tuple(resolved)


def run_verifications(
    *,
    runner=subprocess.run,
    python_executable: str = sys.executable,
    powershell_executable: str | None = AUTO_POWERSHELL,
    stream: TextIO = sys.stdout,
) -> int:
    """Run every step, even after failures, and aggregate the final verdict."""
    if powershell_executable == AUTO_POWERSHELL:
        powershell_executable = shutil.which("pwsh") or shutil.which("powershell")

    results: list[tuple[str, int]] = []
    for spec in STEP_SPECS:
        command = _resolve_command(
            spec,
            python_executable=python_executable,
            powershell_executable=powershell_executable,
        )
        print(f"[EBTA verify] running {spec.name}...", file=stream, flush=True)
        if command is None:
            print(
                f"[EBTA verify] {spec.name}: FAIL (PowerShell host not found)",
                file=stream,
                flush=True,
            )
            results.append((spec.name, 127))
            continue
        try:
            completed = runner(command, cwd=REPO_ROOT, check=False)
            returncode = int(completed.returncode)
        except OSError as error:
            print(f"[EBTA verify] {spec.name}: FAIL ({error})", file=stream, flush=True)
            results.append((spec.name, 127))
            continue
        state = "PASS" if returncode == 0 else "FAIL"
        print(
            f"[EBTA verify] {spec.name}: {state} (exit {returncode})",
            file=stream,
            flush=True,
        )
        results.append((spec.name, returncode))

    print("[EBTA verify] summary", file=stream, flush=True)
    for name, returncode in results:
        state = "PASS" if returncode == 0 else "FAIL"
        print(
            f"[EBTA verify] - {name}: {state} (exit {returncode})",
            file=stream,
            flush=True,
        )
    failed = [name for name, returncode in results if returncode != 0]
    if failed:
        print(
            f"[EBTA verify] VERDICT: FAIL ({', '.join(failed)})",
            file=stream,
            flush=True,
        )
        return 1
    print("[EBTA verify] VERDICT: PASS", file=stream, flush=True)
    return 0


def validate_json_schema(data_path: Path, schema_path: Path) -> int:
    try:
        import jsonschema  # pyrefly: ignore [missing-import]
    except ImportError as error:
        print(f"[EBTA verify] schema validator unavailable: {error}", file=sys.stderr)
        return 2

    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.validate(data, schema)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError, jsonschema.SchemaError) as error:
        print(f"[EBTA verify] schema validation failed: {error}", file=sys.stderr)
        return 1
    print(f"[EBTA verify] {data_path.as_posix()} matches {schema_path.as_posix()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", nargs=2, metavar=("DATA", "SCHEMA"))
    args = parser.parse_args(argv)
    if args.schema is not None:
        data_path, schema_path = (REPO_ROOT / item for item in args.schema)
        return validate_json_schema(data_path, schema_path)
    return run_verifications()


if __name__ == "__main__":
    sys.exit(main())
