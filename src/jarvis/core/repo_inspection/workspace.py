"""Workspace helpers for repository inspection."""

from __future__ import annotations

import os
from pathlib import Path

from .safety import IGNORED_DIRS, is_ignored_dir, is_within_workspace


def resolve_workspace_root(path: str | Path | None = None) -> Path:
    root = Path(path or ".").resolve()
    return root


def ensure_within_workspace(path: Path, workspace_root: Path) -> None:
    if not is_within_workspace(path, workspace_root):
        raise ValueError(f"outside workspace: {path}")


def list_tree_limited(workspace_root: Path, *, max_entries: int) -> tuple[list[Path], list[tuple[Path, str]]]:
    entries: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    for root, dirs, files in os.walk(workspace_root, topdown=True):
        root_path = Path(root)
        kept_dirs: list[str] = []
        for d in sorted(dirs):
            p = root_path / d
            if is_ignored_dir(p):
                skipped.append((p, "ignored_dir"))
                continue
            kept_dirs.append(d)
        dirs[:] = kept_dirs
        for d in kept_dirs:
            p = root_path / d
            if len(entries) >= max_entries:
                skipped.append((p, "limit"))
            else:
                entries.append(p)
        for f in sorted(files):
            p = root_path / f
            if len(entries) >= max_entries:
                skipped.append((p, "limit"))
            else:
                entries.append(p)
    return entries, skipped
