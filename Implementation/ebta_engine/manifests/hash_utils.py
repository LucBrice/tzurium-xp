"""Hash utilities for EBTA manifests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def sha256_tree(root: Path, *, relative_paths: Iterable[str]) -> str:
    """Hash an explicit file tree using stable POSIX paths and file hashes."""
    digest = hashlib.sha256()
    normalized_paths = sorted(Path(path).as_posix() for path in relative_paths)
    if not normalized_paths:
        raise ValueError("tree hash requires at least one file")
    for relative_path in normalized_paths:
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"tree hash path must be relative and contained: {relative_path}")
        file_path = root / path
        if not file_path.is_file():
            raise ValueError(f"tree hash path is not a file: {relative_path}")
        digest.update(f"{relative_path}\n{sha256_file(file_path)}".encode("utf-8"))
    return digest.hexdigest().upper()


def sha256_entries(entries: Iterable[tuple[str, str]]) -> str:
    """Hash sorted identifier/value pairs with the manifest canonical form."""
    digest = hashlib.sha256()
    for identifier, value in sorted(entries):
        digest.update(f"{identifier}\n{value}".encode("utf-8"))
    return digest.hexdigest().upper()
