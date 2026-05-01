"""Deterministic summarizer for repository inspection."""

from __future__ import annotations

from pathlib import Path


def detect_project_type(workspace_root: Path) -> list[str]:
    kinds: list[str] = []
    if (workspace_root / "pyproject.toml").exists() or (workspace_root / "requirements.txt").exists() or (workspace_root / "setup.py").exists():
        kinds.append("python")
    if (workspace_root / "package.json").exists():
        kinds.append("node")
    if (workspace_root / "Cargo.toml").exists():
        kinds.append("rust")
    if (workspace_root / "go.mod").exists():
        kinds.append("go")
    if (workspace_root / "pom.xml").exists() or (workspace_root / "build.gradle").exists():
        kinds.append("java")
    if (workspace_root / "jarvis").exists() or (workspace_root / "src" / "jarvis").exists():
        kinds.append("cli")
        kinds.append("agent")
    if (workspace_root / "src").exists() and (workspace_root / "tests").exists():
        kinds.append("source-tested")
    if (workspace_root / "AGENTS.md").exists() or (workspace_root / "JARVIS.md").exists():
        kinds.append("agent-instructed")
    seen: set[str] = set()
    ordered: list[str] = []
    for k in kinds:
        if k not in seen:
            seen.add(k)
            ordered.append(k)
    return ordered


def detect_entrypoints(tree_entries: list[Path], workspace_root: Path) -> list[str]:
    picks: list[str] = []
    for p in tree_entries:
        if not p.is_file():
            continue
        low = p.name.lower()
        if low in {"cli.py", "main.py", "__main__.py"}:
            picks.append(p.relative_to(workspace_root).as_posix())
    return sorted(dict.fromkeys(picks))


def detect_important_modules(tree_entries: list[Path], workspace_root: Path) -> list[str]:
    dirs = ["src/jarvis/core/routing", "src/jarvis/core/cli_response", "src/jarvis/core/safety_guard.py", "jarvis/cli.py", "src/jarvis/cli.py"]
    found: list[str] = []
    for rel in dirs:
        p = workspace_root / rel
        if p.exists():
            found.append(rel)
    return found


def detect_test_layout(tree_entries: list[Path], workspace_root: Path) -> list[str]:
    found: list[str] = []
    candidates = ["tests", "pytest.ini", "pyproject.toml"]
    for rel in candidates:
        p = workspace_root / rel
        if p.exists():
            found.append(rel)
    return found


def build_architecture_summary(project_type: list[str]) -> str:
    if "python" in project_type and "cli" in project_type:
        return "This repository is a Python CLI-based local coding assistant with routing, safety, and approval flows."
    if "python" in project_type:
        return "This repository is primarily a Python project with source and test structure."
    return "This repository has a mixed structure; key files and modules were inspected in read-only mode."


def build_next_suggestions() -> list[str]:
    return [
        "Implement real small coding smoke.",
        "Add scoped test policy.",
        "Continue sandbox boundary work.",
    ]
