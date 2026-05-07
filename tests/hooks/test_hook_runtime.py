"""Integration tests for hooks running in the tool loop context.

Tests pre/post hooks interacting with ToolRuntime and the unified agent path.
"""

from __future__ import annotations

import pytest

from src.jarvis.core.hooks.schema import HookResult, HookSpec
from src.jarvis.core.hooks.registry import HookRegistry
from src.jarvis.core.tools.schema import ToolCall, ToolContext, ToolResult
from src.jarvis.core.tools.registry import ToolRegistry
from src.jarvis.core.tools.builtin import register_builtin_tools
from src.jarvis.core.tools.runtime import ToolRuntime, ApprovalGate


def _build_runtime(
    permission_mode: str = "workspace_write",
    auto_approve: bool = False,
    hook_registry: HookRegistry | None = None,
) -> ToolRuntime:
    reg = ToolRegistry()
    register_builtin_tools(reg)
    return ToolRuntime(
        registry=reg,
        permission_mode=permission_mode,
        approval_gate=ApprovalGate(auto_approve=auto_approve),
        hook_registry=hook_registry,
    )


class TestPreHookDenies:
    def test_pre_hook_rejects_shell_run(self):
        """A pre_tool_use hook that denies shell.run should produce hook_denied."""
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="no-shell",
            stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
            handler=lambda **kw: HookResult(allowed=False, reason="shell blocked by policy"),
        ))
        runtime = _build_runtime(auto_approve=True, hook_registry=hr)
        call = ToolCall(tool_name="shell.run", arguments={"command": "ls"})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is False
        assert "hook_denied" in result.metadata

    def test_pre_hook_rejects_patch_apply(self):
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="no-patch",
            stage="pre_tool_use",
            matcher={"tool_name": "patch.apply"},
            handler=lambda **kw: HookResult(allowed=False, reason="patch blocked by policy"),
        ))
        runtime = _build_runtime(auto_approve=True, hook_registry=hr)
        call = ToolCall(tool_name="patch.apply", arguments={"file_path": "/tmp/x.py", "content": "x"})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is False
        assert "hook_denied" in result.metadata

    def test_pre_hook_non_matching_does_not_block(self):
        """A hook targeting shell.run should NOT block workspace.status."""
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="no-shell",
            stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
            handler=lambda **kw: HookResult(allowed=False, reason="shell blocked"),
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True


class TestPreHookAllows:
    def test_pre_hook_allows_workspace_status(self):
        """A pre hook that allows workspace.status should not interfere."""
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="audit-status",
            stage="pre_tool_use",
            matcher={"tool_name": "workspace.status"},
            handler=lambda **kw: HookResult(allowed=True),
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True
        assert "root" in str(result.output)

    def test_pre_hook_allows_list_dir(self):
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="audit-list",
            stage="pre_tool_use",
            matcher={"tool_name": "workspace.list_dir"},
            handler=lambda **kw: HookResult(allowed=True),
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.list_dir", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True


class TestPostHookAudit:
    def test_post_hook_audit_called(self):
        """PostToolUse hook should be called and ToolResult should still be ok."""
        audit_log = []

        def audit_handler(**kw):
            tool_result = kw.get("result")
            if tool_result is not None:
                audit_log.append(tool_result.tool_name)

        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="audit",
            stage="post_tool_use",
            matcher={},
            handler=audit_handler,
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True
        assert "workspace.status" in audit_log

    def test_post_hook_exception_does_not_break_result(self):
        """PostToolUse hook that raises should not affect ToolResult."""
        def exploding_post(**kw):
            raise RuntimeError("audit failure")

        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="bad-audit",
            stage="post_tool_use",
            matcher={},
            handler=exploding_post,
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True

    def test_post_hook_called_after_pre_hook(self):
        """Execution order: pre_hook → handler → post_hook."""
        order = []

        def pre_handler(**kw):
            order.append("pre")

        def post_handler(**kw):
            order.append("post")

        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="pre", stage="pre_tool_use", handler=pre_handler,
        ))
        hr.register_spec(HookSpec(
            name="post", stage="post_tool_use", handler=post_handler,
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        runtime.run(call, ctx)
        assert order == ["pre", "post"]
