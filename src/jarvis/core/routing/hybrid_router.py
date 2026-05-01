"""Hybrid natural-language intent router with deterministic + LLM fallback gateway."""

from __future__ import annotations

from pathlib import Path

from ..instructions.schema import InstructionBundle
from ..llm.provider import LLMProvider

from .examples import ROUTING_EXAMPLES
from .intent_gateway import route_user_text
from .schema import IntentRoute


def route_user_input(
    user_input: str,
    *,
    source_surface: str = "cli",
    input_kind: str = "unknown_task",
    workspace_root: Path | None = None,
    session_id: str = "cli_shell",
    instruction_bundle: InstructionBundle | None = None,
    llm_provider: LLMProvider | None = None,
    examples: list[dict[str, object]] | None = None,
) -> IntentRoute:
    return route_user_text(
        user_input,
        source_surface=source_surface,
        input_kind=input_kind,
        workspace_root=workspace_root,
        session_id=session_id,
        instruction_bundle=instruction_bundle,
        llm_provider=llm_provider,
        examples=examples or ROUTING_EXAMPLES,
    )
