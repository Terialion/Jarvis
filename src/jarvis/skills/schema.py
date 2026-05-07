"""Schema objects for Jarvis skill metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


RiskLevelSource = Literal["declared", "inferred", "unknown"]


@dataclass
class SkillSpec:
    name: str
    description: str
    path: str
    source: str
    source_format: str
    allowed_tools: list[str] = field(default_factory=list)
    raw_allowed_tools: str | list[str] | None = None
    risk_level: str = "unknown"
    risk_level_source: RiskLevelSource = "unknown"
    read_when: list[str] = field(default_factory=list)
    always_apply: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    external_metadata: dict[str, Any] = field(default_factory=dict)
    body_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_index_row(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "source_format": self.source_format,
            "risk_level": self.risk_level,
            "risk_level_source": self.risk_level_source,
            "raw_allowed_tools": self.raw_allowed_tools,
            "allowed_tools": list(self.allowed_tools),
            "read_when": list(self.read_when),
            "always_apply": self.always_apply,
            "path": self.path,
        }
