"""Subagent tool handlers for spawn/wait/list/close.

These are standalone functions that ToolRegistryAdapter wires into tool specs.
They receive the SubagentPool from the tool context so they work with any pool instance.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..tools.schema import ToolContext as CoreToolContext
from ..tools.schema import ToolResult as CoreToolResult
from .models import SubagentConfig
from .policy import check_depth


def handle_spawn_agent(
    arguments: dict[str, Any],
    context: CoreToolContext,
    pool: Any,
) -> CoreToolResult:
    """Spawn a subagent that runs asynchronously. Returns immediately with agent_id."""
    task = str(arguments.get("task") or "").strip()
    if not task:
        return CoreToolResult(
            tool_name="spawn_agent",
            ok=False,
            error="spawn_agent requires a non-empty task.",
            metadata={"error_code": "empty_task"},
        )

    agent_type = str(arguments.get("agent_type") or "general-purpose")
    if agent_type not in ("Explore", "Plan", "general-purpose"):
        return CoreToolResult(
            tool_name="spawn_agent",
            ok=False,
            error=f"Unknown agent_type: {agent_type}. Use Explore, Plan, or general-purpose.",
            metadata={"error_code": "invalid_agent_type"},
        )

    requested_depth = int(arguments.get("depth") or 0)
    depth_check = check_depth(requested_depth, pool.max_depth)
    if not depth_check["ok"]:
        return CoreToolResult(
            tool_name="spawn_agent",
            ok=False,
            error=depth_check["error"]["message"],
            metadata={"error_code": depth_check["error"]["code"]},
        )

    budget = int(arguments.get("budget_steps") or 10)
    agent_id = f"sub_{uuid4().hex[:12]}"

    config = SubagentConfig(
        agent_id=agent_id,
        agent_type=agent_type,
        task=task,
        parent_run_id=context.session_id or "",
        budget_steps=min(max(1, budget), 20),
        depth=requested_depth,
    )

    handle = pool.submit(config)

    return CoreToolResult(
        tool_name="spawn_agent",
        ok=handle.status.value != "failed",
        output=f"Subagent {agent_id} spawned ({agent_type}). Status: {handle.status.value}.",
        metadata={
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": handle.status.value,
            "depth": requested_depth,
            "active_count": pool.active_count(),
        },
    )


def handle_wait_agent(
    arguments: dict[str, Any],
    context: CoreToolContext,
    pool: Any,
) -> CoreToolResult:
    """Block until a specific subagent completes."""
    agent_id = str(arguments.get("agent_id") or "").strip()
    if not agent_id:
        return CoreToolResult(
            tool_name="wait_agent",
            ok=False,
            error="wait_agent requires an agent_id.",
            metadata={"error_code": "missing_agent_id"},
        )

    timeout = float(arguments.get("timeout") or 60.0)
    result = pool.wait_agent(agent_id, timeout=timeout)

    if result["status"] == "not_found":
        return CoreToolResult(
            tool_name="wait_agent",
            ok=False,
            error=f"Agent {agent_id} not found.",
            metadata={"error_code": "agent_not_found"},
        )

    completed = result["status"] in ("completed", "failed", "cancelled")
    return CoreToolResult(
        tool_name="wait_agent",
        ok=completed,
        output=result.get("result", result.get("error", "")) if completed else f"Agent {agent_id} still running...",
        metadata={
            "agent_id": agent_id,
            "status": result["status"],
            "active_count": pool.active_count(),
        },
    )


def handle_list_agents(
    arguments: dict[str, Any],
    context: CoreToolContext,
    pool: Any,
) -> CoreToolResult:
    """List all subagents and their statuses."""
    agents = pool.list_agents()
    summary_lines = []
    for a in agents:
        mark = "●" if a["status"] == "running" else "○"  # ● or ○
        summary_lines.append(
            f"{mark} {a['agent_id']} [{a['agent_type']}] {a['status']} "
            f"({a['steps']}/{a['max_steps']} steps, depth={a['depth']})"
        )

    return CoreToolResult(
        tool_name="list_agents",
        ok=True,
        output="\n".join(summary_lines) if summary_lines else "No agents.",
        metadata={
            "agents": agents,
            "active_count": pool.active_count(),
            "spawn_count": pool.spawn_count,
            "completed_count": pool.completed_count,
            "failed_count": pool.failed_count,
        },
    )


def handle_close_agent(
    arguments: dict[str, Any],
    context: CoreToolContext,
    pool: Any,
) -> CoreToolResult:
    """Cancel a running subagent."""
    agent_id = str(arguments.get("agent_id") or "").strip()
    if not agent_id:
        return CoreToolResult(
            tool_name="close_agent",
            ok=False,
            error="close_agent requires an agent_id.",
            metadata={"error_code": "missing_agent_id"},
        )

    cancelled = pool.close_agent(agent_id)
    return CoreToolResult(
        tool_name="close_agent",
        ok=cancelled,
        output=f"Agent {agent_id} {'cancelled' if cancelled else 'could not be cancelled (not running or not found)'}.",
        metadata={"agent_id": agent_id, "cancelled": cancelled},
    )
