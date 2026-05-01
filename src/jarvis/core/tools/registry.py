"""ToolRegistry — central registry for all tools available to the agent."""

from __future__ import annotations

from typing import Any

from .schema import ToolSpec


class ToolRegistry:
    """Central registry for tool specifications.

    Tools are registered as ToolSpec instances. The registry provides:
    - List all tools (for LLM prompt injection)
    - Get tool spec by name
    - Check if a tool exists
    - Generate LLM-visible tool summary
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """Register a tool specification."""
        if not spec.name:
            raise ValueError("ToolSpec must have a non-empty name")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        """Get a tool specification by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_all(self) -> list[ToolSpec]:
        """List all registered tool specs."""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """List all registered tool names."""
        return sorted(self._tools.keys())

    def to_llm_tool_context(self) -> str:
        """Generate a tool summary string for LLM prompt injection.

        This includes tool names, descriptions, schemas, risks, and permissions.
        It does NOT include handler functions.
        """
        tools = self.list_all()
        if not tools:
            return "No tools available."

        lines = ["## Available Tools\n"]
        for t in sorted(tools, key=lambda x: x.name):
            summary = t.to_llm_summary()
            lines.append(f"### {t.name}")
            lines.append(f"  description: {t.description}")
            lines.append(f"  risk_level: {t.risk_level}")
            lines.append(f"  requires_approval: {t.requires_approval}")
            lines.append(f"  permissions: {', '.join(summary['permissions'])}")
            if t.input_schema.get("properties"):
                lines.append("  input_schema:")
                for pname, pinfo in t.input_schema.get("properties", {}).items():
                    req = "required" if pname in t.input_schema.get("required", []) else "optional"
                    desc = pinfo.get("description", "")
                    lines.append(f"    - {pname} ({req}): {desc}")
            lines.append("")
        return "\n".join(lines)

    def to_llm_json(self) -> list[dict[str, Any]]:
        """Return tool summaries as a list of dicts for JSON serialization."""
        return [t.to_llm_summary() for t in sorted(self.list_all(), key=lambda x: x.name)]

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"<ToolRegistry: {len(self)} tools>"
