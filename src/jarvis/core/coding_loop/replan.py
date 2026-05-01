from __future__ import annotations

from src.jarvis.core.instructions.schema import InstructionBundle
from src.jarvis.core.llm.provider import LLMProvider

from .schema import CodingLoopState, RethinkRecord


def replan_from_rethink(
    state: CodingLoopState,
    rethink_record: RethinkRecord,
    *,
    instructions: InstructionBundle | None = None,
    llm_provider: LLMProvider | None = None,
) -> list[str]:
    _ = instructions, llm_provider
    if rethink_record.revised_plan:
        return list(rethink_record.revised_plan)
    if state.current_plan:
        return list(state.current_plan)
    return [
        "Inspect target fixture and failing test.",
        "Prepare minimal patch.",
        "Run scoped fixture tests.",
    ]
