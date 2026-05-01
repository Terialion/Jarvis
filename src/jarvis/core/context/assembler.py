from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AssembledContext:
    workspace_root: Path | None
    session_id: str | None
    instruction_sources: list[str] = field(default_factory=list)
    skill_names: list[str] = field(default_factory=list)
    command_names: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def assemble_context(
    *,
    workspace_root: Path | None,
    session_id: str | None,
    instruction_sources: list[str] | None = None,
    skill_names: list[str] | None = None,
    command_names: list[str] | None = None,
) -> AssembledContext:
    return AssembledContext(
        workspace_root=workspace_root,
        session_id=session_id,
        instruction_sources=list(instruction_sources or []),
        skill_names=list(skill_names or []),
        command_names=list(command_names or []),
        notes=["Context scaffold only. Full compact/resume remains a later sprint."],
    )

