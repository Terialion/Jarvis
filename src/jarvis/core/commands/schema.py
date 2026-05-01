from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CommandMetadata:
    name: str
    description: str
    argument_hint: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    dispatch: Literal["local", "agent", "tool"] = "local"
    risk_level: str = "low"

