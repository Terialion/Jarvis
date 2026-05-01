"""Central CommandRegistry — single source of truth for all slash commands.

CLI, gateway, and Web UI must share this registry.
Commands not in the registry must return "unsupported" or "unknown",
never enter the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from ...cli_command_map import CliCommandSpec, list_command_specs, resolve_command, suggest_commands


@dataclass(frozen=True)
class CommandSpec:
    """Central command specification.

    This is the single source of truth for all slash commands.
    CLI, gateway, and Web UI must use this registry.
    """

    name: str
    aliases: list[str]
    description: str
    argument_hint: str | None
    dispatch: Literal["local", "agent", "tool", "skill"]
    allowed_tools: list[str]
    risk_level: str
    status: Literal["implemented", "skeleton", "unsupported"]
    handler: Callable | None = None


class CommandRegistry:
    """Central command registry.

    All slash commands are registered here. The CLI and any future
    gateway / Web UI must use this registry exclusively.
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandSpec] = {}
        self._aliases: dict[str, str] = {}

    def register(self, spec: CommandSpec) -> None:
        """Register a command."""
        self._commands[spec.name] = spec
        for alias in spec.aliases:
            self._aliases[alias] = spec.name

    def get(self, name: str) -> CommandSpec | None:
        """Get a command by name or alias."""
        if not name.startswith("/"):
            name = f"/{name}"
        canonical = self._aliases.get(name, name)
        return self._commands.get(canonical)

    def has(self, name: str) -> bool:
        """Check if a command is registered."""
        return self.get(name) is not None

    def list_all(self) -> list[CommandSpec]:
        """List all registered commands."""
        return list(self._commands.values())

    def list_names(self) -> list[str]:
        """List all command names."""
        return sorted(self._commands.keys())

    def list_implemented(self) -> list[CommandSpec]:
        """List only implemented commands."""
        return [c for c in self._commands.values() if c.status == "implemented"]

    def resolve(self, raw: str) -> CommandSpec | None:
        """Resolve a raw command string (with or without /) to a CommandSpec."""
        return self.get(raw)

    def suggest(self, raw: str) -> list[str]:
        """Suggest similar command names for unknown commands."""
        from difflib import get_close_matches

        name = raw.lstrip("/")
        all_names = [c.name.lstrip("/") for c in self._commands.values()]
        matches = get_close_matches(name, all_names, n=3, cutoff=0.4)
        return [f"/{m}" if not m.startswith("/") else m for m in matches]

    def __len__(self) -> int:
        return len(self._commands)

    def __repr__(self) -> str:
        return f"<CommandRegistry: {len(self)} commands>"


def build_command_registry() -> CommandRegistry:
    """Build the central CommandRegistry from existing CliCommandSpec data.

    This bridges the existing cli_command_map.py to the new central registry.
    Future: commands should be registered directly here.
    """
    registry = CommandRegistry()

    # Map of dispatch types
    _TOOL_COMMANDS = {"/approve", "/reject", "/test"}
    _AGENT_COMMANDS = {"/fix", "/review", "/plan"}

    for spec in list_command_specs():
        # Determine dispatch type
        if spec.name in _TOOL_COMMANDS:
            dispatch: Literal["local", "agent", "tool", "skill"] = "tool"
        elif spec.name in _AGENT_COMMANDS:
            dispatch = "agent"
        elif spec.status == "implemented":
            dispatch = "local"
        else:
            dispatch = "local"

        # Determine status
        if spec.status == "implemented":
            status: Literal["implemented", "skeleton", "unsupported"] = "implemented"
        elif spec.status == "skeleton":
            status = "skeleton"
        else:
            status = "unsupported"

        # Determine allowed_tools
        allowed_tools: list[str] = []
        if spec.name in {"/approve", "/reject"}:
            allowed_tools = ["approval.resolve"]
        elif spec.name == "/test":
            allowed_tools = ["shell.run_scoped_tests"]
        elif spec.name == "/fix":
            allowed_tools = ["coding_loop.patch"]
        elif spec.name == "/review":
            allowed_tools = ["diff.review"]
        elif spec.name == "/plan":
            allowed_tools = ["repo.inspect", "planning.generate"]

        # Determine risk_level
        if spec.safety in {"approval_required", "disabled"}:
            risk = "high"
        elif spec.safety == "ask":
            risk = "medium"
        else:
            risk = "low"

        cmd = CommandSpec(
            name=spec.name,
            aliases=list(spec.aliases),
            description=spec.description,
            argument_hint=spec.examples[0] if spec.examples else None,
            dispatch=dispatch,
            allowed_tools=allowed_tools,
            risk_level=risk,
            status=status,
        )
        registry.register(cmd)

    return registry
