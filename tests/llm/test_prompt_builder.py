from jarvis.core.instructions.schema import InstructionBundle, InstructionSource
from jarvis.core.llm.prompt_builder import (
    build_coding_plan_prompt,
    build_final_review_prompt,
    build_intent_classification_prompt,
    build_natural_response_prompt,
    build_repo_inspection_summary_prompt,
    build_rethink_replan_prompt,
    build_success_judge_prompt,
)


def _bundle() -> InstructionBundle:
    return InstructionBundle(
        sources=[InstructionSource(scope="project", path="JARVIS.md", loaded=True, bytes=12)],
        combined_text="Project says use scoped tests.",
    )


def test_prompt_builder_includes_instruction_bundle_and_constraints() -> None:
    prompt = build_coding_plan_prompt(instructions=_bundle(), user_goal="fix bug")
    assert "Project says use scoped tests." in prompt
    assert "Do not bypass safety" in prompt
    assert "fix bug" in prompt


def test_all_prompt_builders_return_contextual_prompts() -> None:
    bundle = _bundle()
    prompts = [
        build_natural_response_prompt(instructions=bundle, response_mode="help_answer", user_input="what can you do"),
        build_repo_inspection_summary_prompt(instructions=bundle, user_input="inspect", result={"ok": True}),
        build_success_judge_prompt(instructions=bundle, state={"stop_reason": "test_failed"}),
        build_rethink_replan_prompt(instructions=bundle, state={}, observation={"summary": "failed"}),
        build_final_review_prompt(instructions=bundle, result={"stop_reason": "done"}),
        build_intent_classification_prompt(
            instructions=bundle,
            user_input="write a python file",
            envelope={"language": "en"},
            examples=[{"input": "write code", "expected_intent": "coding_task"}],
        ),
    ]
    assert all("Project says use scoped tests." in item for item in prompts)
    assert any("Return strict JSON only." in item for item in prompts)
