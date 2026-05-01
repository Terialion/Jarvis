from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..skills.command_registry import list_user_invocable_skill_commands, resolve_user_invocable_skill_command
from ..skills.metadata import SkillCommandMetadata
from .input_gateway import InputEnvelope


@dataclass
class SkillCommandRoute:
    handled: bool
    response_mode: str
    candidate_skill: str | None = None
    raw_args: str = ""
    inject_skill_context: bool = False
    requires_approval: bool = False
    requires_tools: list[str] | None = None
    trace: dict[str, Any] | None = None


def route_skill_command(
    envelope: InputEnvelope,
    *,
    registry_items: list[dict[str, Any]] | None = None,
) -> SkillCommandRoute:
    slash = envelope.slash
    if not slash.is_slash_command or not slash.command_name:
        return SkillCommandRoute(handled=False, response_mode="not_skill_command")

    command_name = slash.command_name
    if command_name == "skill":
        if not slash.args_tokens:
            return SkillCommandRoute(handled=False, response_mode="not_skill_command")
        skill_name = slash.args_tokens[0]
        args = " ".join(slash.args_tokens[1:]).strip()
        metadata = resolve_user_invocable_skill_command(skill_name, registry_items=registry_items)
        if metadata is None:
            return SkillCommandRoute(handled=False, response_mode="not_skill_command")
        return _build_skill_route(metadata, args=args, trigger=f"/skill {skill_name}")

    metadata = resolve_user_invocable_skill_command(command_name, registry_items=registry_items)
    if metadata is None:
        return SkillCommandRoute(handled=False, response_mode="not_skill_command")
    return _build_skill_route(metadata, args=slash.raw_args, trigger=f"/{command_name}")


def _build_skill_route(metadata: SkillCommandMetadata, *, args: str, trigger: str) -> SkillCommandRoute:
    base_trace = {
        "input_kind": "skill_command",
        "command_name": metadata.command_name,
        "candidate_skill": metadata.name,
        "raw_args": args,
        "entered_llm": metadata.command_dispatch != "tool",
        "dispatch": metadata.command_dispatch or "model",
        "trigger": trigger,
    }
    if metadata.command_dispatch == "tool":
        return SkillCommandRoute(
            handled=True,
            response_mode="skill_tool_dispatch",
            candidate_skill=metadata.name,
            raw_args=args,
            inject_skill_context=False,
        requires_approval=metadata.risk_level in {"medium", "high", "critical"},
        requires_tools=[metadata.command_tool] if metadata.command_tool else [],
        trace=base_trace,
    )
    return SkillCommandRoute(
        handled=True,
        response_mode="skill_agent",
        candidate_skill=metadata.name,
        raw_args=args,
        inject_skill_context=True,
        requires_approval=metadata.risk_level in {"medium", "high", "critical"},
        requires_tools=[],
        trace=base_trace,
    )
