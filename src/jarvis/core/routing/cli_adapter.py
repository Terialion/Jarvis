"""Adapter helpers for CLI integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..instructions.loader import load_project_instructions
from ..instructions.schema import InstructionBundle
from ..llm.provider import LLMProvider

from .examples import ROUTING_EXAMPLES
from .hybrid_router import route_user_input
from .safety_gate import apply_route_safety
from .trace import append_intent_route_trace


def build_cli_route(
    user_input: str,
    *,
    mode: str,
    input_kind: str,
    instruction_bundle: InstructionBundle | None = None,
    llm_provider: LLMProvider | None = None,
) -> dict[str, Any]:
    workspace_root = Path.cwd()
    route_before = route_user_input(
        user_input,
        source_surface="cli",
        input_kind=input_kind,
        workspace_root=workspace_root,
        instruction_bundle=instruction_bundle or load_project_instructions(workspace_root),
        llm_provider=llm_provider,
        examples=ROUTING_EXAMPLES,
    )
    route_after = apply_route_safety(route_before, user_input, mode=mode)
    return {
        "route_before_safety": route_before.to_dict(),
        "route_after_safety": route_after.to_dict(),
    }


def write_cli_trace(
    *,
    trace_path: Path,
    timestamp: str,
    user_input: str,
    route_before_safety: dict[str, Any],
    route_after_safety: dict[str, Any],
    final_response_mode: str,
    entered_task_flow: bool,
    notes: str,
) -> None:
    append_intent_route_trace(
        trace_path=trace_path,
        timestamp=timestamp,
        session_id="cli_shell",
        source_surface="cli",
        user_input=user_input,
        route_before_safety=route_before_safety,
        safety_decision=route_after_safety.get("safety_decision", {}),
        route_after_safety=route_after_safety,
        final_response_mode=final_response_mode,
        entered_task_flow=entered_task_flow,
        notes=notes,
    )
