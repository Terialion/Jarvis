"""Tests for ToolRuntime safety — focused on safety boundary enforcement."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.jarvis.core.tools.schema import ToolCall, ToolContext, ToolResult
from src.jarvis.core.tools.registry import ToolRegistry
from src.jarvis.core.tools.builtin import register_builtin_tools
from src.jarvis.core.tools.runtime import ApprovalGate, ToolRuntime
from src.jarvis.core.hooks.schema import HookResult


class TestToolRuntimeHooks:
    def test_pre_hook_can_deny(self):
        """PreToolUse hook can deny a tool call."""
        reg = ToolRegistry()
        register_builtin_tools(reg)

        def deny_shell(spec, call, context):
            if spec.name == "shell.run":
                return HookResult(allowed=False, reason="shell blocked by test hook")

        rt = ToolRuntime(
            registry=reg,
            permission_mode="danger_full_access",
            approval_gate=ApprovalGate(auto_approve=True),
            pre_hooks=[deny_shell],
        )
        call = ToolCall(tool_name="shell.run", arguments={"command": "echo hello"})
        result = rt.run(call)
        assert result.ok is False
        assert "hook_denied" in result.error

    def test_post_hook_cannot_modify_result(self):
        """PostToolUse hook can observe but cannot modify the result."""

        observations = []

        def observe(spec, call, result, context):
            observations.append((spec.name, result.ok))

        reg = ToolRegistry()
        register_builtin_tools(reg)
        rt = ToolRuntime(
            registry=reg,
            permission_mode="read_only",
            post_hooks=[observe],
        )
        call = ToolCall(tool_name="workspace.status", arguments={})
        result = rt.run(call)
        assert result.ok is True
        assert len(observations) == 1
        assert observations[0] == ("workspace.status", True)

    def test_post_hook_error_does_not_affect_result(self):
        """PostToolUse hook errors are swallowed."""

        def broken_hook(spec, call, result, context):
            raise RuntimeError("intentional error")

        reg = ToolRegistry()
        register_builtin_tools(reg)
        rt = ToolRuntime(
            registry=reg,
            permission_mode="read_only",
            post_hooks=[broken_hook],
        )
        call = ToolCall(tool_name="workspace.status", arguments={})
        result = rt.run(call)
        # Result should still be ok — post hook errors are swallowed
        assert result.ok is True

    def test_multiple_pre_hooks_first_deny_wins(self):
        """If first pre hook denies, second is not called."""
        call_order = []

        def allow_hook(spec, call, context):
            call_order.append("allow")
            return HookResult(allowed=True)

        def deny_hook(spec, call, context):
            call_order.append("deny")
            return HookResult(allowed=False, reason="denied")

        reg = ToolRegistry()
        register_builtin_tools(reg)
        rt = ToolRuntime(
            registry=reg,
            permission_mode="danger_full_access",
            approval_gate=ApprovalGate(auto_approve=True),
            pre_hooks=[deny_hook, allow_hook],
        )
        call = ToolCall(tool_name="shell.run", arguments={"command": "echo hi"})
        result = rt.run(call)
        assert result.ok is False
        assert call_order == ["deny"]
