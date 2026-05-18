from __future__ import annotations

from dataclasses import asdict

from ...cli_command_map import CliCommandSpec, list_command_specs, resolve_command
from .schema import CommandMetadata

_LOCAL_COMMANDS = {
    "/help",
    "/context",
    "/threads",
    "/resume",
    "/compact",
    "/continue",
    "/skills",
    "/tools",
    "/model",
    "/exit",
}
_TOOL_COMMANDS = {
    "/approve": ["approval.resolve"],
    "/deny": ["approval.resolve"],
    "/reject": ["approval.resolve"],
    "/test": ["shell.run_scoped_tests"],
}
_AGENT_COMMANDS = {
    "/fix": ["file_editor.replace_text"],
    "/review": ["diff.review"],
    "/plan": ["repo.inspect", "planning.generate"],
}


def _normalize(name: str) -> str:
    item = str(name or "").strip()
    if not item:
        return ""
    return item if item.startswith("/") else f"/{item}"


def _dispatch_for(name: str) -> str:
    normalized = _normalize(name).lower()
    if normalized in _TOOL_COMMANDS:
        return "tool"
    if normalized in _AGENT_COMMANDS:
        return "agent"
    return "local"


def _allowed_tools_for(name: str) -> list[str]:
    normalized = _normalize(name).lower()
    if normalized in _TOOL_COMMANDS:
        return list(_TOOL_COMMANDS[normalized])
    if normalized in _AGENT_COMMANDS:
        return list(_AGENT_COMMANDS[normalized])
    return []


def _argument_hint_for(spec: CliCommandSpec) -> str | None:
    if spec.examples:
        example = str(spec.examples[0]).strip()
        parts = example.split(maxsplit=1)
        if len(parts) == 2:
            return parts[1]
    return None


def list_command_metadata() -> list[CommandMetadata]:
    rows: list[CommandMetadata] = []
    for spec in list_command_specs():
        rows.append(
            CommandMetadata(
                name=spec.name,
                description=spec.description,
                argument_hint=_argument_hint_for(spec),
                allowed_tools=_allowed_tools_for(spec.name),
                dispatch=_dispatch_for(spec.name),
                risk_level="high" if spec.safety in {"approval_required", "disabled"} else ("medium" if spec.safety == "ask" else "low"),
            )
        )
    return rows


def resolve_command_metadata(name: str) -> CommandMetadata | None:
    spec = resolve_command(_normalize(name)) or resolve_command(str(name or "").strip())
    if spec is None:
        return None
    return CommandMetadata(
        name=spec.name,
        description=spec.description,
        argument_hint=_argument_hint_for(spec),
        allowed_tools=_allowed_tools_for(spec.name),
        dispatch=_dispatch_for(spec.name),
        risk_level="high" if spec.safety in {"approval_required", "disabled"} else ("medium" if spec.safety == "ask" else "low"),
    )


def reserved_command_names() -> set[str]:
    return {item.name.lstrip("/").lower() for item in list_command_metadata()}


def command_metadata_json() -> list[dict[str, object]]:
    return [asdict(item) for item in list_command_metadata()]

