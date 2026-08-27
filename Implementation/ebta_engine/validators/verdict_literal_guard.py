"""AST ratchet for positive literals written to governed verdict sinks.

This is a syntax inventory, not a scientific authority. Protected names are
exact contract keys; no substring or suffix heuristic is used.
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeGuard

from ebta_engine.validators.gate_validator import GATE_REQUIREMENTS


ALLOWLIST_SCHEMA_VERSION = "1.0.0"
POSITIVE_STRING = "PASS"
EXCLUDED_PATH_PARTS = frozenset({"tests", "fixtures", "research_packages", "__pycache__", "venv"})
PERSISTED_VERDICT_KEYS = frozenset(
    {
        "status",
        "verdict",
        "decision_status",
        "statistical_status",
        "economic_status",
        "global_status",
        "statistical",
        "economic",
        "final",
    }
)
ECONOMIC_HURDLE_KEYS = frozenset(
    {
        "return_hurdle_pass",
        "drawdown_pass",
        "capacity_pass",
        "costs_pass",
        "execution_pass",
    }
)
ALLOWED_CATEGORIES = frozenset(
    {
        "derived_calculation",
        "expected_contract",
        "controlled_fixture",
        "technical_attestation",
        "human_constant",
        "structural_event",
    }
)


@dataclass(frozen=True)
class LiteralCandidate:
    fingerprint: str
    path: str
    scope: str
    sink: str
    literal: str
    line: int


def protected_sink_keys() -> frozenset[str]:
    gate_keys = {
        requirement.name
        for requirements in GATE_REQUIREMENTS.values()
        for requirement in requirements
        if requirement.kind != "identifier"
    }
    return frozenset(gate_keys | PERSISTED_VERDICT_KEYS | ECONOMIC_HURDLE_KEYS)


def scan_source(
    source: str,
    *,
    relative_path: str,
    protected_keys: frozenset[str] | None = None,
) -> list[LiteralCandidate]:
    tree = ast.parse(source, filename=relative_path)
    keys = protected_keys or protected_sink_keys()
    parents: dict[ast.AST, ast.AST] = {}
    scopes: dict[ast.AST, str] = {}
    scope_stack: list[str] = []

    class _Index(ast.NodeVisitor):
        def generic_visit(self, node: ast.AST) -> None:
            scopes[node] = ".".join(scope_stack) or "<module>"
            for child in ast.iter_child_nodes(node):
                parents[child] = node
            super().generic_visit(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            scope_stack.append(node.name)
            self.generic_visit(node)
            scope_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            scope_stack.append(node.name)
            self.generic_visit(node)
            scope_stack.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            scope_stack.append(node.name)
            self.generic_visit(node)
            scope_stack.pop()

    _Index().visit(tree)
    grouped: dict[tuple[str, str, str], list[ast.Constant]] = {}
    for node in ast.walk(tree):
        if not _is_positive_literal(node):
            continue
        sink = _nearest_protected_sink(node, parents, keys)
        if sink is None:
            continue
        literal = "true" if node.value is True else "PASS"
        group_key = (scopes.get(node, "<module>"), sink, literal)
        grouped.setdefault(group_key, []).append(node)

    candidates: list[LiteralCandidate] = []
    for (scope, sink, literal), nodes in sorted(grouped.items()):
        ordered = sorted(nodes, key=lambda item: (item.lineno, item.col_offset))
        for ordinal, node in enumerate(ordered, start=1):
            fingerprint = f"{relative_path}::{scope}::{sink}::{literal}::{ordinal}"
            candidates.append(
                LiteralCandidate(
                    fingerprint=fingerprint,
                    path=relative_path,
                    scope=scope,
                    sink=sink,
                    literal=literal,
                    line=node.lineno,
                )
            )
    return sorted(candidates, key=lambda candidate: candidate.fingerprint)


def scan_repository(repo_root: Path) -> list[LiteralCandidate]:
    resolved_root = repo_root.resolve()
    scan_roots = (
        repo_root / "Implementation" / "ebta_engine",
        repo_root / "Implementation" / "ebta_private",
        repo_root / "Implementation" / "examples",
        repo_root / "Implementation" / "adapters",
    )
    source_paths = {
        path
        for scan_root in scan_roots
        if scan_root.exists()
        for path in scan_root.rglob("*.py")
        if not any(part in EXCLUDED_PATH_PARTS for part in path.relative_to(repo_root).parts)
    }
    candidates: list[LiteralCandidate] = []
    for path in sorted(source_paths):
        if path.is_symlink():
            continue
        resolved_path = path.resolve()
        if not resolved_path.is_relative_to(resolved_root):
            continue
        relative_path = path.relative_to(repo_root).as_posix()
        candidates.extend(
            scan_source(
                path.read_text(encoding="utf-8"),
                relative_path=relative_path,
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.fingerprint)


def load_allowlist(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("verdict literal allowlist must be a JSON object")
    return payload


def audit_allowlist(candidates: list[LiteralCandidate], allowlist: dict[str, Any]) -> dict[str, Any]:
    format_errors = _allowlist_format_errors(allowlist)
    entries = allowlist.get("entries", []) if isinstance(allowlist, dict) else []
    allowed_fingerprints = {
        entry.get("fingerprint")
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("fingerprint"), str)
    }
    by_fingerprint = {candidate.fingerprint: candidate for candidate in candidates}
    candidate_fingerprints = set(by_fingerprint)
    unapproved = [asdict(by_fingerprint[item]) for item in sorted(candidate_fingerprints - allowed_fingerprints)]
    stale = sorted(allowed_fingerprints - candidate_fingerprints)
    expected_count = allowlist.get("expected_count") if isinstance(allowlist, dict) else None
    count_mismatch = expected_count != len(candidates)
    status = POSITIVE_STRING if not (format_errors or unapproved or stale or count_mismatch) else "FAIL"
    return {
        "status": status,
        "candidate_count": len(candidates),
        "expected_count": expected_count,
        "count_mismatch": count_mismatch,
        "format_errors": format_errors,
        "unapproved": unapproved,
        "stale": stale,
    }


def _allowlist_format_errors(allowlist: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if allowlist.get("schema_version") != ALLOWLIST_SCHEMA_VERSION:
        errors.append(f"schema_version must be {ALLOWLIST_SCHEMA_VERSION}")
    expected_count = allowlist.get("expected_count")
    if not isinstance(expected_count, int) or isinstance(expected_count, bool) or expected_count < 0:
        errors.append("expected_count must be a non-negative integer")
    entries = allowlist.get("entries")
    if not isinstance(entries, list):
        return [*errors, "entries must be a list"]
    if isinstance(expected_count, int) and not isinstance(expected_count, bool) and len(entries) != expected_count:
        errors.append("entries length must equal expected_count")
    fingerprints: list[str] = []
    required_fields = {"fingerprint", "category", "justification", "decision_source"}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entries[{index}] must be an object")
            continue
        if set(entry) != required_fields:
            errors.append(f"entries[{index}] must contain exactly {sorted(required_fields)}")
        fingerprint = entry.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint.strip():
            errors.append(f"entries[{index}].fingerprint must be a non-empty string")
        else:
            fingerprints.append(fingerprint)
        if entry.get("category") not in ALLOWED_CATEGORIES:
            errors.append(f"entries[{index}].category is invalid")
        for field in ("justification", "decision_source"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"entries[{index}].{field} must be a non-empty string")
    if len(fingerprints) != len(set(fingerprints)):
        errors.append("allowlist fingerprints must be unique")
    return errors


def _is_positive_literal(node: ast.AST) -> TypeGuard[ast.Constant]:
    return isinstance(node, ast.Constant) and (node.value is True or node.value == POSITIVE_STRING)


def _nearest_protected_sink(
    node: ast.Constant,
    parents: dict[ast.AST, ast.AST],
    protected_keys: frozenset[str],
) -> str | None:
    child: ast.AST = node
    while child in parents:
        parent = parents[child]
        if isinstance(parent, ast.keyword):
            return f"keyword:{parent.arg}" if parent.arg in protected_keys else None
        if isinstance(parent, ast.Dict):
            key = _dict_key_for_descendant(parent, node)
            return f"dict:{key}" if key in protected_keys else None
        if isinstance(parent, ast.Assign):
            target_keys: list[str] = []
            for target in parent.targets:
                target_key = _target_key(target)
                if target_key is not None and target_key in protected_keys:
                    target_keys.append(target_key)
            return f"assign:{','.join(target_keys)}" if target_keys else None
        if isinstance(parent, ast.AnnAssign):
            target_key = _target_key(parent.target)
            return f"assign:{target_key}" if target_key in protected_keys else None
        child = parent
    return None


def _dict_key_for_descendant(node: ast.Dict, descendant: ast.AST) -> str | None:
    for key, value in zip(node.keys, node.values, strict=True):
        if value is descendant or any(child is descendant for child in ast.walk(value)):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return key.value
            return None
    return None


def _target_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        slice_node = node.slice
        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
            return slice_node.value
    return None


def main(argv: list[str] | None = None) -> int:
    repo_root_default = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=repo_root_default)
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=repo_root_default / "Implementation" / "ebta_engine" / "tests" / "verdict_literal_allowlist.json",
    )
    args = parser.parse_args(argv)
    report = audit_allowlist(scan_repository(args.repo_root), load_allowlist(args.allowlist))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == POSITIVE_STRING else 1


if __name__ == "__main__":
    raise SystemExit(main())
