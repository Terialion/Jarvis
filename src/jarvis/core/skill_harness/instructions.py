"""Project-instruction discovery and lightweight policy extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..jarvis_rules_loader import JarvisRulesLoader


MAX_PROJECT_INSTRUCTION_BYTES = 32768
PROJECT_INSTRUCTION_FILES = ("JARVIS.md", "AGENTS.md", "AGENTS.override.md", ".jarvis/AGENTS.md", ".jarvis/JARVIS.md")


@dataclass
class ProjectInstructionContext:
    sources: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    blocked_skills: list[str] = field(default_factory=list)
    preferred_test_commands: list[str] = field(default_factory=list)
    docs_only: bool = False
    no_network: bool = False
    file_write_allowed: bool = True
    require_approval: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": list(self.sources),
            "forbidden_tools": list(self.forbidden_tools),
            "preferred_skills": list(self.preferred_skills),
            "blocked_skills": list(self.blocked_skills),
            "preferred_test_commands": list(self.preferred_test_commands),
            "docs_only": bool(self.docs_only),
            "no_network": bool(self.no_network),
            "file_write_allowed": bool(self.file_write_allowed),
            "require_approval": bool(self.require_approval),
            "notes": list(self.notes),
        }


def load_project_instruction_context(project_root: str | Path | None = None) -> ProjectInstructionContext:
    root = Path(project_root or ".").resolve()
    context = ProjectInstructionContext()
    loader = JarvisRulesLoader()
    jarvis_rules = loader.load(str(root))
    if jarvis_rules.get("ok"):
        data = dict(jarvis_rules.get("data") or {})
        if data.get("rules_found"):
            context.sources.append(str(root / "JARVIS.md"))
            context.preferred_test_commands.extend(list(data.get("test_commands") or []))
            for rule in list(data.get("forbidden_actions") or []):
                low = str(rule).lower()
                if "network" in low:
                    context.no_network = True
                if "full pytest" in low:
                    context.preferred_test_commands.append("never_full_pytest")
    for rel in PROJECT_INSTRUCTION_FILES:
        path = root / rel
        if not path.exists() or not path.is_file():
            continue
        text = _read_limited(path, MAX_PROJECT_INSTRUCTION_BYTES)
        if not text:
            continue
        context.sources.append(str(path))
        _extract_policy_hints(text, context)
    context.sources = list(dict.fromkeys(context.sources))
    context.forbidden_tools = _dedupe(context.forbidden_tools)
    context.preferred_skills = _dedupe(context.preferred_skills)
    context.blocked_skills = _dedupe(context.blocked_skills)
    context.preferred_test_commands = _dedupe(context.preferred_test_commands)
    context.notes = _dedupe(context.notes)
    return context


def _read_limited(path: Path, max_bytes: int) -> str:
    try:
        data = path.read_bytes()[:max_bytes]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_policy_hints(text: str, context: ProjectInstructionContext) -> None:
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "do not use network" in low or "no-network" in low or "never use network" in low:
            context.no_network = True
            context.notes.append("instruction:no_network")
        if "docs-only" in low or "docs only" in low:
            context.docs_only = True
            context.file_write_allowed = True
            context.notes.append("instruction:docs_only")
        if "do not modify files" in low:
            context.file_write_allowed = False
            context.require_approval = True
            context.notes.append("instruction:no_file_write")
        if "never run full pytest" in low or "do not run full pytest" in low:
            context.preferred_test_commands.append("never_full_pytest")
        if "require approval" in low or "approval required" in low:
            context.require_approval = True
        match_pref_skill = re.search(r"prefer\s+([a-zA-Z0-9_.-]+)", line, flags=re.IGNORECASE)
        if match_pref_skill:
            context.preferred_skills.append(match_pref_skill.group(1).strip().lower())
        match_block_skill = re.search(r"block(?:ed)?\s+skill\s+([a-zA-Z0-9_.-]+)", line, flags=re.IGNORECASE)
        if match_block_skill:
            context.blocked_skills.append(match_block_skill.group(1).strip().lower())
        if "forbidden tools" in low or "forbid tools" in low:
            tools = re.split(r"[:,]", line, maxsplit=1)
            if len(tools) == 2:
                for item in re.split(r"[,\s]+", tools[1]):
                    token = item.strip().lower()
                    if token and token not in {"and", "or"}:
                        context.forbidden_tools.append(token)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out
