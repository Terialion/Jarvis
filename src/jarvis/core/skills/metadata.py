from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SkillCommandMetadata:
    name: str
    command_name: str
    description: str
    user_invocable: bool
    command_dispatch: Literal["tool", "model", None]
    command_tool: str | None
    risk_level: str

