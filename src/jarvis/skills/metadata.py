"""Skill metadata extraction and capability index."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schema import SkillSpec, SkillType


@dataclass
class SkillMetadata:
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    when_to_use: str = ""
    location: str = ""
    skill_type: SkillType = "unknown"
    entrypoint: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    risk_level: str = "unknown"
    trust_state: str = "untrusted"
    enabled_state: bool = True
    quarantine_state: bool = False
    source: str = "unknown"

    @classmethod
    def from_spec(cls, spec: SkillSpec, *, lifecycle_state: dict[str, Any] | None = None) -> "SkillMetadata":
        state = dict(lifecycle_state or {})
        return cls(
            name=spec.name,
            description=spec.description,
            tags=list(spec.tags),
            capabilities=list(spec.capabilities),
            examples=list(spec.examples),
            when_to_use=spec.when_to_use,
            location=spec.path,
            skill_type=spec.skill_type,
            entrypoint=spec.entrypoint,
            allowed_tools=list(spec.allowed_tools),
            risk_level=spec.risk_level,
            trust_state=str(state.get("trust") or "untrusted"),
            enabled_state=bool(state.get("enabled", True)),
            quarantine_state=bool(state.get("quarantined", False)),
            source=spec.source,
        )

    def to_compact_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "skill_type": self.skill_type,
            "tags": self.tags,
            "capabilities": self.capabilities,
            "risk_level": self.risk_level,
            "source": self.source,
        }

    def is_active(self) -> bool:
        return self.enabled_state and not self.quarantine_state


class CapabilityIndex:
    """Index of all skill capabilities for fast matching lookups."""

    def __init__(self) -> None:
        self._entries: dict[str, SkillMetadata] = {}

    def build(self, specs: list[SkillSpec], lifecycle_states: dict[str, dict[str, Any]]) -> "CapabilityIndex":
        self._entries = {}
        for spec in specs:
            state = lifecycle_states.get(spec.name, {})
            meta = SkillMetadata.from_spec(spec, lifecycle_state=state)
            self._entries[spec.name] = meta
        return self

    def active_entries(self) -> list[SkillMetadata]:
        return [m for m in self._entries.values() if m.is_active()]

    def get(self, name: str) -> SkillMetadata | None:
        return self._entries.get(name)

    def search_by_tag(self, tag: str) -> list[SkillMetadata]:
        lowered = tag.lower()
        return [m for m in self.active_entries() if lowered in m.tags]

    def search_by_capability(self, capability: str) -> list[SkillMetadata]:
        lowered = capability.lower()
        return [m for m in self.active_entries() if any(lowered in c for c in m.capabilities)]

    def to_compact_list(self) -> list[dict[str, Any]]:
        return [m.to_compact_dict() for m in self.active_entries()]
