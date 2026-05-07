from __future__ import annotations

from .hooks import HookDefinition, HookRegistry


def default_security_hook_registry() -> HookRegistry:
    registry = HookRegistry()
    registry.register(
        HookDefinition(
            name="warn-high-risk-tools",
            hook_type="pre_tool_use",
            matcher={"tool_name": ["command_runner.run", "file_editor.replace_text", "test_runner.run_test", "web.fetch"]},
            action="warn",
            message="High-risk tool invocation recorded for audit.",
        )
    )
    registry.register(
        HookDefinition(
            name="record-tool-result",
            hook_type="post_tool_use",
            matcher={},
            action="record",
            message="Tool result recorded for audit.",
        )
    )
    registry.register(
        HookDefinition(
            name="warn-result-secret-like",
            hook_type="post_tool_use",
            matcher={"contains_secret_text": True},
            action="warn",
            message="Tool result contained secret-like content and was redacted.",
        )
    )
    return registry
