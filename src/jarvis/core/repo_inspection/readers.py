"""File selection and read helpers for repository inspection."""

from __future__ import annotations

from pathlib import Path

from .safety import is_likely_binary, is_sensitive_path
from .schema import ReadFileRecord, SkippedFileRecord

KEY_FILE_NAMES = [
    "README.md",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "Dockerfile",
    "AGENTS.md",
    "JARVIS.md",
]


def select_key_files(workspace_root: Path, tree_entries: list[Path]) -> list[Path]:
    files = [p for p in tree_entries if p.is_file()]
    selected: list[Path] = []
    for p in sorted(files):
        if p.parent == workspace_root:
            selected.append(p)
            if len(selected) >= 10:
                break
    for name in KEY_FILE_NAMES:
        p = workspace_root / name
        if p.exists() and p.is_file():
            selected.append(p)
    for prefix in ["src", "jarvis", "tests", "scripts", "docs"]:
        base = workspace_root / prefix
        if base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file() and p.suffix in {".py", ".md", ".toml", ".json", ".yaml", ".yml"}:
                    selected.append(p)
                    if len([x for x in selected if x.is_file()]) >= 30:
                        break
    # Keep deterministic order and deduplicate.
    uniq: dict[str, Path] = {}
    for p in selected:
        uniq[p.resolve().as_posix()] = p
    return list(uniq.values())


def read_text_file_limited(
    path: Path,
    *,
    max_file_bytes: int,
    remaining_budget: int,
) -> tuple[str | None, ReadFileRecord | None, SkippedFileRecord | None]:
    if is_sensitive_path(path):
        return None, None, SkippedFileRecord(path=path.as_posix(), reason="sensitive")
    try:
        raw = path.read_bytes()
    except Exception:
        return None, None, SkippedFileRecord(path=path.as_posix(), reason="read_error")
    if len(raw) > max_file_bytes:
        return None, None, SkippedFileRecord(path=path.as_posix(), reason="too_large")
    if len(raw) > remaining_budget:
        return None, None, SkippedFileRecord(path=path.as_posix(), reason="limit")
    if is_likely_binary(raw):
        return None, None, SkippedFileRecord(path=path.as_posix(), reason="binary")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, None, SkippedFileRecord(path=path.as_posix(), reason="decode_error")
    return text, ReadFileRecord(path=path.as_posix(), bytes_read=len(raw)), None
