"""Safety rules for read-only repository inspection."""

from __future__ import annotations

from pathlib import Path

IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".cache",
}

SENSITIVE_HINTS = [
    ".env",
    ".ssh",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "credential",
    "token",
    "tokens",
    "secret",
    "secrets",
    "key.pem",
    ".pem",
    ".key",
    "npmrc",
    ".pypirc",
    ".netrc",
]


def is_within_workspace(path: Path, workspace_root: Path) -> bool:
    try:
        path.resolve().relative_to(workspace_root.resolve())
        return True
    except Exception:
        return False


def is_ignored_dir(path: Path) -> bool:
    return path.name.lower() in IGNORED_DIRS


def is_sensitive_path(path: Path) -> bool:
    low = path.as_posix().lower()
    if path.name.lower().startswith(".env"):
        return True
    return any(token in low for token in SENSITIVE_HINTS)


def is_likely_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data:
        return True
    non_text = sum(1 for b in data if b < 9 or (13 < b < 32))
    return (non_text / max(1, len(data))) > 0.3
