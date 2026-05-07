from __future__ import annotations

from src.jarvis.core.policy.hooks import HookDefinition, HookInput, HookRegistry


def test_posttool_hook_can_warn():
    registry = HookRegistry(
        hooks=[HookDefinition(name="warn-read", hook_type="post_tool_use", matcher={"tool_name": "repo_reader.read_file"}, action="warn", message="warn")]
    )
    results = registry.run_post_tool_use(
        HookInput(
            hook_type="post_tool_use",
            tool_name="repo_reader.read_file",
            arguments_preview={"path": "README.md"},
            result_preview={"content": "ok"},
            context={"risk_level": "low"},
        )
    )
    assert results
    assert results[0][1].action == "warn"
