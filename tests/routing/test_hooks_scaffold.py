from src.jarvis.core.hooks import HookResult, HookStage, HookStageRegistry


def test_hook_scaffold_exposes_expected_stages():
    assert HookStage.USER_PROMPT_SUBMIT.value == "user_prompt_submit"
    assert HookStage.PRE_TOOL_USE.value == "pre_tool_use"
    assert HookStage.POST_TOOL_USE.value == "post_tool_use"
    assert HookStage.STOP.value == "stop"


def test_hook_stage_registry_defaults_to_noop_behavior():
    registry = HookStageRegistry()
    result = registry.run(HookStage.USER_PROMPT_SUBMIT, {"text": "hello"})
    assert isinstance(result, HookResult)
    assert result.allowed is True
