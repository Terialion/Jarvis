from src.jarvis.core.coding_loop.replan import replan_from_rethink
from src.jarvis.core.coding_loop.rethink import rethink_after_failure
from src.jarvis.core.coding_loop.schema import CodingLoopState, Observation
from src.jarvis.core.instructions.schema import InstructionBundle
from src.jarvis.core.llm.provider import FakeLLMProvider


def test_rethink_uses_instruction_aware_llm_explanation() -> None:
    provider = FakeLLMProvider(response="Prefer the smallest scoped patch.", prompts=[])
    state = CodingLoopState(task_id="t", workspace_root=".", user_goal="fix")
    state.round = 1
    state.current_plan = ["old plan"]
    obs = Observation(round=1, type="test_result", ok=False, summary="failed")

    record = rethink_after_failure(
        state,
        obs,
        instructions=InstructionBundle(combined_text="Use scoped tests."),
        llm_provider=provider,
    )
    new_plan = replan_from_rethink(state, record, instructions=InstructionBundle(combined_text="Use scoped tests."), llm_provider=provider)

    assert "LLM note" in record.diagnosis
    assert new_plan == record.revised_plan
    assert provider.prompts

