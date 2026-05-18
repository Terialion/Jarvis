from __future__ import annotations

from typing import Any


MUTATING_TOOLS = {"coding.fix"}


def is_mutating_tool(name: str) -> bool:
    return name in MUTATING_TOOLS


def filter_tools_for_profile(tools: list[dict[str, Any]], profile: str) -> list[dict[str, Any]]:
    if profile not in {"strict", "read_only"}:
        return tools
    allowed = {"agent.run", "coding.review", "coding.test", "coding.fix"} if profile == "strict" else {"agent.run", "coding.review", "coding.test"}
    return [tool for tool in tools if str(tool.get("name") or "") in allowed]


def can_call_tool(profile: str, name: str) -> bool:
    if profile not in {"strict", "read_only"}:
        return True
    if profile == "strict":
        return name in {"agent.run", "coding.review", "coding.test", "coding.fix"}
    return name in {"agent.run", "coding.review", "coding.test"}
