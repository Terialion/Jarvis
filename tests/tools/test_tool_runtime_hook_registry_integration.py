"""Integration tests for ToolRuntime + HookRegistry.

Verifies that the HookRegistry integrates correctly into the ToolRuntime
execution chain without breaking existing behavior.
"""

from __future__ import annotations

import pytest

from src.jarvis.core.hooks.schema import HookResult, HookSpec
from src.jarvis.core.hooks.registry import HookRegistry
from src.jarvis.core.tools.schema import ToolCall, ToolContext
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


class TestRuntimeWithHookRegistry:
    def test_runtime_with_hook_registry_pre_deny(self):
        """PreToolUse hook denies → hook_denied in ToolResult."""
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="block-shell",
            stage="pre_tool_use",
            matcher={"tool_name": "shell.run"},
            handler=lambda **kw: HookResult(allowed=False, reason="policy: no shell"),
        ))
        runtime = _build_runtime(auto_approve=True, hook_registry=hr)
        call = ToolCall(tool_name="shell.run", arguments={"command": "echo hi"})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is False
        assert "hook_denied" in result.metadata
        assert "policy: no shell" in result.error

    def test_runtime_with_hook_registry_pre_allow(self):
        """PreToolUse hook allows → normal execution proceeds."""
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="allow-status",
            stage="pre_tool_use",
            matcher={"tool_name": "workspace.status"},
            handler=lambda **kw: HookResult(allowed=True),
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True

    def test_runtime_with_hook_registry_post_audit(self):
        """PostToolUse hook records execution, ToolResult still ok."""
        audit_log = []

        def audit(**kw):
            audit_log.append(kw.get("call", {}).tool_name if hasattr(kw.get("call", {}), "tool_name") else "unknown")

        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="audit",
            stage="post_tool_use",
            matcher={},
            handler=audit,
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True
        assert len(audit_log) == 1

    def test_runtime_without_hook_registry_works(self):
        """Runtime works normally without HookRegistry (backward compat)."""
        runtime = _build_runtime(hook_registry=None)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True

    def test_hook_registry_post_error_does_not_break_result(self):
        """Post hook raising Exception → ToolResult still returned correctly."""
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="bad-post",
            stage="post_tool_use",
            matcher={},
            handler=lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True
        assert result.tool_name == "workspace.status"

    def test_hook_registry_pre_error_treated_as_denial(self):
        """Pre hook raising Exception → treated as denial."""
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="crash-pre",
            stage="pre_tool_use",
            matcher={"tool_name": "workspace.list_dir"},
            handler=lambda **kw: (_ for _ in ()).throw(ValueError("crash")),
        ))
        runtime = _build_runtime(hook_registry=hr)
        call = ToolCall(tool_name="workspace.list_dir", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is False
        assert "hook_denied" in result.metadata

    def test_hook_registry_with_legacy_hooks_both_run(self):
        """Legacy pre_hooks and HookRegistry both run in order."""
        order = []

        def legacy_pre(spec, call, context):
            order.append("legacy_pre")

        def registry_pre(**kw):
            order.append("registry_pre")
            return HookResult(allowed=True)

        def legacy_post(spec, call, result, context):
            order.append("legacy_post")

        def registry_post(**kw):
            order.append("registry_post")

        hr = HookRegistry()
        hr.register_spec(HookSpec(name="rp", stage="pre_tool_use", handler=registry_pre))
        hr.register_spec(HookSpec(name="rpost", stage="post_tool_use", handler=registry_post))

        reg = ToolRegistry()
        register_builtin_tools(reg)
        runtime = ToolRuntime(
            registry=reg,
            permission_mode="workspace_write",
            pre_hooks=[legacy_pre],
            post_hooks=[legacy_post],
            hook_registry=hr,
        )
        call = ToolCall(tool_name="workspace.status", arguments={})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        assert result.ok is True
        assert order == ["legacy_pre", "registry_pre", "legacy_post", "registry_post"]

    def test_hook_registry_does_not_affect_approval_gate(self):
        """HookRegistry pre-hook cannot bypass ApprovalGate."""
        hr = HookRegistry()
        hr.register_spec(HookSpec(
            name="allow-all",
            stage="pre_tool_use",
            matcher={},
            handler=lambda **kw: HookResult(allowed=True),
        ))
        # auto_approve=False, shell.run requires approval
        runtime = _build_runtime(auto_approve=False, hook_registry=hr)
        call = ToolCall(tool_name="shell.run", arguments={"command": "ls"})
        ctx = ToolContext(permission_mode="workspace_write")
        result = runtime.run(call, ctx)
        # Should be blocked by ApprovalGate, NOT by hook
        assert result.ok is False
        assert "approval_required" in result.error
