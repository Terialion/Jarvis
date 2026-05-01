from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...cli_command_map import suggest_commands
from ..commands.registry import resolve_command_metadata
from .input_gateway import InputEnvelope


@dataclass
class CommandRoute:
    handled: bool
    response_mode: str
    command_name: str | None = None
    raw_args: str = ""
    args_tokens: list[str] = field(default_factory=list)
    entered_llm: bool = False
    message: str = ""
    trace: dict[str, Any] = field(default_factory=dict)


def route_command(envelope: InputEnvelope) -> CommandRoute:
    slash = envelope.slash
    if not slash.is_slash_command:
        return CommandRoute(handled=False, response_mode="not_command")
    command_name = slash.command_name or ""
    metadata = resolve_command_metadata(command_name)
    if slash.is_unknown_command and metadata is None:
        suggestions = [item if item.startswith("/") else f"/{item}" for item in suggest_commands(f"/{command_name}")]
        hint = "Try /help." if not suggestions else f"Did you mean: {', '.join(suggestions)}"
        return CommandRoute(
            handled=True,
            response_mode="command_result",
            command_name=command_name,
            raw_args=slash.raw_args,
            args_tokens=list(slash.args_tokens),
            message=f"Unknown command: /{command_name}\n{hint}",
            trace=_trace(envelope, command_name, handled=True, unknown=True),
        )
    return CommandRoute(
        handled=True,
        response_mode="command_result" if metadata is None else f"command_{metadata.dispatch}",
        command_name=command_name,
        raw_args=slash.raw_args,
        args_tokens=list(slash.args_tokens),
        message="",
        trace=_trace(envelope, command_name, handled=True, unknown=False, dispatch=None if metadata is None else metadata.dispatch),
    )


def _trace(
    envelope: InputEnvelope,
    command_name: str,
    *,
    handled: bool,
    unknown: bool,
    dispatch: str | None = None,
) -> dict[str, Any]:
    return {
        "input_kind": "slash",
        "command_name": command_name,
        "raw_args": envelope.slash.raw_args,
        "entered_llm": False,
        "handled": handled,
        "unknown_command": unknown,
        "dispatch": dispatch or "local",
    }
