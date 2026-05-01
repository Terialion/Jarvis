from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..commands.registry import list_command_metadata
from ..commands.schema import CommandMetadata
from ..skills.command_registry import list_user_invocable_skill_commands
from ..skills.metadata import SkillCommandMetadata
from .input_gateway import InputEnvelope


@dataclass
class PreparedNaturalInput:
    envelope: InputEnvelope
    workspace_root: Path | None
    session_id: str | None
    url_hints: list[str] = field(default_factory=list)
    path_hints: list[str] = field(default_factory=list)
    sensitive_hints: list[str] = field(default_factory=list)
    command_metadata: list[CommandMetadata] = field(default_factory=list)
    skill_metadata: list[SkillCommandMetadata] = field(default_factory=list)
    repo_summary_hint: str = "repo summary placeholder"


def prepare_natural_input(
    envelope: InputEnvelope,
    *,
    command_metadata: list[CommandMetadata] | None = None,
    skill_metadata: list[SkillCommandMetadata] | None = None,
) -> PreparedNaturalInput:
    return PreparedNaturalInput(
        envelope=envelope,
        workspace_root=envelope.workspace_root,
        session_id=envelope.session_id,
        url_hints=list(envelope.urls),
        path_hints=list(envelope.path_hints),
        sensitive_hints=list(envelope.sensitive_hints),
        command_metadata=list(command_metadata or list_command_metadata()),
        skill_metadata=list(skill_metadata or list_user_invocable_skill_commands()),
    )
