from __future__ import annotations

from src.jarvis.core.policy.hooks import HookDefinition, HookInput, HookRegistry


def test_pretool_hook_can_deny():
    registry = HookRegistry(
        hooks=[HookDefinition(name="deny-shell", hook_type="pre_tool_use", matcher={"tool_name": "command_runner.run"}, action="deny", message="blocked")]
    )
    results = registry.run_pre_tool_use(
        HookInput(
            hook_type="pre_tool_use",
            tool_name="command_runner.run",
            arguments_preview={"command": "python -V"},
            result_preview=None,
            context={"risk_level": "high"},
        )
    )
    assert results
    assert results[0][1].action == "deny"
