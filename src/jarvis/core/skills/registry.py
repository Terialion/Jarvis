"""Skill specification and registry for the core skill system.

Key concepts:
- SkillSpec: structured metadata about a skill
- SkillRegistry: central registry with progressive disclosure
- Progressive disclosure: LLM sees metadata first, full SKILL.md only on invoke
- Trust boundary: installed != trusted; untrusted skills cannot shell/network/write
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class SkillSpec:
    """Structured specification for a registered skill.

    LLM sees: name, description, metadata summary, allowed_tools, risk_level, trust_level.
    LLM does NOT see: full_instructions until explicitly invoked.
    """

    name: str
    description: str
    path: Path
    metadata: dict[str, Any]
    allowed_tools: list[str]
    risk_level: str
    trust_level: Literal["untrusted", "local", "trusted"]
    installed: bool
    enabled: bool
    full_instructions_loaded: bool = False
    _full_instructions: str | None = field(default=None, repr=False)

    def to_llm_summary(self) -> dict[str, Any]:
        """Return a description visible to the LLM (no full instructions)."""
        return {
            "name": self.name,
            "description": self.description,
            "allowed_tools": list(self.allowed_tools),
            "risk_level": self.risk_level,
            "trust_level": self.trust_level,
            "installed": self.installed,
            "enabled": self.enabled,
        }

    def get_full_instructions(self) -> str | None:
        """Load and return full SKILL.md instructions (progressive disclosure)."""
        if self.full_instructions_loaded:
            return self._full_instructions
        # Try to load from path
        skill_md = self.path / "SKILL.md" if self.path.is_dir() else self.path
        if skill_md.exists():
            try:
                self._full_instructions = skill_md.read_text(encoding="utf-8", errors="replace")
                self.full_instructions_loaded = True
                return self._full_instructions
            except Exception:
                return None
        return None


class SkillRegistry:
    """Central registry for skills with progressive disclosure.

    LLM sees metadata only. Full SKILL.md is loaded on demand.
    Trust boundaries are enforced: untrusted skills cannot shell/network/write.
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillSpec] = {}

    def register(self, spec: SkillSpec) -> None:
        """Register a skill."""
        self._skills[spec.name] = spec

    def get(self, name: str) -> SkillSpec | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        """Check if a skill is registered."""
        return name in self._skills

    def list_all(self) -> list[SkillSpec]:
        """List all registered skills."""
        return list(self._skills.values())

    def list_enabled(self) -> list[SkillSpec]:
        """List only enabled skills."""
        return [s for s in self._skills.values() if s.enabled]

    def list_names(self) -> list[str]:
        """List all skill names."""
        return sorted(self._skills.keys())

    def to_llm_skill_context(self) -> str:
        """Generate skill summary for LLM prompt (metadata only)."""
        skills = self.list_enabled()
        if not skills:
            return "No skills available."

        lines = ["## Available Skills\n"]
        for s in sorted(skills, key=lambda x: x.name):
            summary = s.to_llm_summary()
            lines.append(f"- {s.name}: {s.description}")
            lines.append(f"  trust_level: {s.trust_level}, risk: {s.risk_level}")
        return "\n".join(lines)

    def check_trust(self, name: str, requested_tools: list[str]) -> tuple[bool, str | None]:
        """Check if a skill is allowed to use requested tools based on trust level.

        Returns (allowed, reason) tuple.
        """
        spec = self.get(name)
        if spec is None:
            return False, f"skill_not_found: {name}"

        if not spec.enabled:
            return False, f"skill_disabled: {name}"

        # Untrusted skills cannot shell, network, or write
        if spec.trust_level == "untrusted":
            dangerous_tools = {"shell", "network", "write", "bash", "edit"}
            for tool in requested_tools:
                if any(dangerous in tool.lower() for dangerous in dangerous_tools):
                    return False, f"trust_denied: untrusted skill '{name}' cannot use '{tool}'"

        # Check against allowed_tools (can only narrow, never expand)
        if spec.allowed_tools:
            for tool in requested_tools:
                if tool not in spec.allowed_tools:
                    return False, f"tool_not_allowed: '{tool}' is not in skill's allowed_tools"

        return True, None

    def __len__(self) -> int:
        return len(self._skills)

    def __repr__(self) -> str:
        return f"<SkillRegistry: {len(self)} skills>"
