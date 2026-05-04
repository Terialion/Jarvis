"""CLI adapter for AgentToolLoop integration — DEPRECATED.

.. deprecated::
    This module is DEPRECATED. Default runtime path uses AgentLoop.run_turn()
    via run_agent_turn_for_cli() instead of AgentToolLoop.
    This module is ONLY reachable via JARVIS_CLI_LEGACY_NL=1 legacy path.
    Deletion target: after ToolCallExecutor parity confirmed.

This module provides the bridge between the CLI dispatcher and AgentToolLoop.
It:
1. Creates a ToolRegistry with builtin tools
2. Creates a ToolRuntime with safety/approval/sandbox
3. Creates an AgentToolLoop
4. Uses AgentRequestRouter to determine chat vs work path
5. For work requests, executes through ToolRuntime
6. Returns results in the dispatcher's expected format
"""

from __future__ import annotations

import logging
from typing import Any

from ..tools.schema import ToolContext
from ..tools.registry import ToolRegistry
from ..tools.builtin import register_builtin_tools
from ..tools.runtime import ToolRuntime, ApprovalGate
from ..tools.loop import AgentToolLoop, LoopResult
from ..routing.agent_router import route_agent_request
from ..llm.runtime_provider import build_runtime_llm_provider

logger = logging.getLogger(__name__)


def build_default_tool_loop(
    permission_mode: str = "workspace_write",
    auto_approve: bool = False,
    llm_provider: Any = None,
    max_rounds: int = 10,
) -> AgentToolLoop:
    """Build a default AgentToolLoop with builtin tools.

    Args:
        permission_mode: Permission mode (read_only, workspace_write, danger_full_access).
        auto_approve: Whether to auto-approve tool calls (for testing/non-interactive).
        llm_provider: Optional LLM provider for work-path execution.
        max_rounds: Maximum rounds for the tool loop.

    Returns:
        Configured AgentToolLoop instance.
    """
    registry = ToolRegistry()
    register_builtin_tools(registry)

    runtime = ToolRuntime(
        registry=registry,
        permission_mode=permission_mode,
        approval_gate=ApprovalGate(auto_approve=auto_approve),
    )

    if llm_provider is None:
        llm_provider = build_runtime_llm_provider()

    return AgentToolLoop(
        registry=registry,
        runtime=runtime,
        llm_provider=llm_provider,
        max_rounds=max_rounds,
    )


def execute_agent_tool_loop(
    user_input: str,
    *,
    tool_loop: AgentToolLoop | None = None,
    permission_mode: str = "workspace_write",
    auto_approve: bool = False,
    llm_provider: Any = None,
) -> tuple[str, bool, str]:
    """Execute a user request through AgentToolLoop.

    This is the main entry point for CLI integration.

    Args:
        user_input: Raw user input text.
        tool_loop: Pre-built AgentToolLoop (if None, creates default).
        permission_mode: Permission mode for default loop creation.
        auto_approve: Auto-approve for default loop creation.
        llm_provider: LLM provider for default loop creation.

    Returns:
        (response_text, is_dangerous, summary) tuple matching dispatcher contract.
    """
    if tool_loop is None:
        tool_loop = build_default_tool_loop(
            permission_mode=permission_mode,
            auto_approve=auto_approve,
            llm_provider=llm_provider,
        )

    context = ToolContext(permission_mode=permission_mode)
    result = tool_loop.execute(user_input, context)

    # Determine if the result involved dangerous operations
    is_dangerous = (
        any(s.error in ("safety_refusal",) for s in result.steps)
        or result.exhausted
    )

    summary = _build_summary(result)
    return result.response, is_dangerous, summary


def _build_summary(result: LoopResult) -> str:
    """Build a human-readable summary of the loop execution."""
    if result.error == "safety_refusal":
        return "safety_refusal"
    if result.exhausted:
        return f"exhausted_after_{result.total_rounds}_rounds"
    if result.total_tool_calls > 0:
        return f"{result.total_rounds}_rounds_{result.total_tool_calls}_tool_calls"
    if result.total_rounds > 0:
        return f"{result.total_rounds}_rounds_chat"
    return "no_execution"


def classify_for_tool_loop(user_input: str) -> dict[str, Any]:
    """Classify a user request for AgentToolLoop routing.

    Uses the deterministic AgentRequestRouter (no LLM needed).
    Returns the routing info as a dict suitable for the dispatcher.

    Args:
        user_input: Raw user input text.

    Returns:
        Dict with routing information.
    """
    agent_request = route_agent_request(user_input)

    # Map agent_request to response_mode format compatible with dispatcher
    if agent_request.response_mode == "refusal_or_safety_message":
        return {
            "response_mode": "refusal_or_safety_message",
            "is_work_request": False,
            "reason": agent_request.reason,
        }

    if agent_request.is_work_request:
        return {
            "response_mode": "agent_tool_loop",
            "is_work_request": True,
            "work_type": agent_request.work_type,
            "required_tools": agent_request.required_tools,
            "requires_approval": agent_request.requires_approval,
            "risk_level": agent_request.risk_level,
            "reason": agent_request.reason,
        }

    # Chat path — pass through to existing renderers
    return {
        "response_mode": agent_request.response_mode or "chat_answer",
        "is_work_request": False,
        "chat_type": agent_request.chat_type,
        "reason": agent_request.reason,
    }
