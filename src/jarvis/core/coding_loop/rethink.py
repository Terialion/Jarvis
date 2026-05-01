from __future__ import annotations

from dataclasses import asdict

from src.jarvis.core.instructions.schema import InstructionBundle
from src.jarvis.core.llm.prompt_builder import build_rethink_replan_prompt
from src.jarvis.core.llm.provider import LLMProvider, safe_complete

from .schema import CodingLoopState, Observation, RethinkRecord


def rethink_after_failure(
    state: CodingLoopState,
    observation: Observation,
    *,
    instructions: InstructionBundle | None = None,
    llm_provider: LLMProvider | None = None,
) -> RethinkRecord:
    trigger = "low_confidence"
    if observation.type == "test_result" and not observation.ok:
        trigger = "test_failed"
    elif observation.type == "patch_result" and not observation.ok:
        trigger = "patch_failed"
    elif observation.type == "inspection_result":
        trigger = "missing_context"

    diagnosis = "Need narrower fix and rerun scoped tests."
    learning_signal = "none"
    revised_plan = list(state.current_plan)
    if trigger == "test_failed":
        diagnosis = "First fix did not satisfy test expectations; revise implementation."
        revised_plan = [
            "Inspect failing assertion and fixture file.",
            "Apply corrected patch for greeting/add behavior.",
            "Run scoped tests only for fixture.",
        ]
        learning_signal = "test_policy_gap"
    elif trigger == "patch_failed":
        diagnosis = "Patch context mismatch; re-inspect file before second attempt."
        revised_plan = [
            "Re-read target file and confirm exact buggy line.",
            "Generate new minimal patch with stable context.",
            "Run scoped tests after approval.",
        ]

    note = safe_complete(
        llm_provider,
        build_rethink_replan_prompt(
            instructions=instructions,
            state={"task_id": state.task_id, "round": state.round, "current_plan": state.current_plan},
            observation=asdict(observation),
        ),
        system="Explain the rethink diagnosis. Do not approve actions or change safety policy.",
    )
    if note:
        diagnosis = f"{diagnosis} LLM note: {note[:240]}"

    return RethinkRecord(
        round=state.round,
        trigger=trigger,
        previous_plan=list(state.current_plan),
        observation_summary=observation.summary,
        diagnosis=diagnosis,
        revised_plan=revised_plan,
        learning_signal=learning_signal,
    )
