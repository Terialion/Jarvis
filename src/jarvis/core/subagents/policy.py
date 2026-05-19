"""Subagent policy: tool restriction by agent_type and depth control."""

from __future__ import annotations

from typing import FrozenSet

# Tool whitelists by agent_type (matching Codex agent_type taxonomy)
EXPLORE_TOOLS: FrozenSet[str] = frozenset({
    "repo_reader.read_file",
    "repo_reader.glob",
    "repo_reader.grep",
    "repo_reader.search_files",
    "repo_reader.search_symbol",
    "repo_reader.list_tree",
})

PLAN_TOOLS: FrozenSet[str] = frozenset({
    "repo_reader.read_file",
    "repo_reader.glob",
    "repo_reader.grep",
    "repo_reader.search_files",
    "repo_reader.search_symbol",
    "repo_reader.list_tree",
    "task.create",
    "task.update",
    "task.list",
})

GENERAL_TOOLS: FrozenSet[str] | None = None  # None = all tools allowed

TOOL_WHITELISTS = {
    "Explore": EXPLORE_TOOLS,
    "Plan": PLAN_TOOLS,
    "general-purpose": GENERAL_TOOLS,
}

DEFAULT_MAX_DEPTH = 2


def tool_whitelist_for_type(agent_type: str) -> FrozenSet[str] | None:
    """Return the allowed tool set for a given agent_type.

    Returns None if all tools are allowed (general-purpose).
    Returns an empty frozenset if the agent_type is unknown (no tools allowed).
    """
    return TOOL_WHITELISTS.get(agent_type, frozenset())


def check_depth(requested_depth: int, max_depth: int = DEFAULT_MAX_DEPTH) -> dict:
    """Check if the requested depth is within limits."""
    if requested_depth > max_depth:
        return {
            "ok": False,
            "error": {
                "code": "MAX_SPAWN_DEPTH_EXCEEDED",
                "message": f"Depth {requested_depth} exceeds max depth {max_depth}",
            },
        }
    return {"ok": True, "data": {"depth": requested_depth}}


def validate_subtask_budget(budget_steps: int) -> dict:
    if budget_steps <= 0:
        return {"ok": False, "error": {"code": "SUBAGENT_INVALID_BUDGET", "message": "budget_steps must be > 0"}}
    if budget_steps > 50:
        return {"ok": False, "error": {"code": "SUBAGENT_INVALID_BUDGET", "message": "budget_steps too high"}}
    return {"ok": True, "data": {"budget_steps": budget_steps}}
