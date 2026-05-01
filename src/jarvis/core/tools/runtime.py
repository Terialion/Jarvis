"""ToolRuntime — unified tool execution with safety, approval, sandbox, and hooks.

Execution chain:
1. SafetyGate — blocks dangerous operations (cannot be overridden)
2. PermissionPolicy — checks if action is allowed in current mode
3. ApprovalGate — checks if approval is needed/granted
4. HookRegistry PreToolUse — run before tool execution
5. Handler — execute the tool
6. HookRegistry PostToolUse — run after tool execution (audit only)
7. Return ToolResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..hooks.schema import HookResult
from ..policy.permissions import PermissionMode, READ_ONLY, get_permission_mode
from ..policy.safety import SafetyGate, SafetyCheckResult
from .schema import ToolCall, ToolContext, ToolResult, ToolSpec
from .registry import ToolRegistry

if TYPE_CHECKING:
    from ..hooks.registry import HookRegistry


@dataclass
class ApprovalStatus:
    granted: bool
    reason: str | None = None


class ApprovalGate:
    """Checks if a tool call needs approval and whether it's been granted."""

    def __init__(self, auto_approve: bool = False) -> None:
        self.auto_approve = auto_approve

    def check(self, spec: ToolSpec, call: ToolCall, context: ToolContext) -> ApprovalStatus:
        """Check approval status for a tool call."""
        mode = get_permission_mode(context.permission_mode)

        # If the tool requires approval AND the permission mode says approval is needed
        if spec.requires_approval:
            if not self.auto_approve:
                return ApprovalStatus(
                    granted=False,
                    reason=f"approval_required: {spec.name} requires approval before execution",
                )

        # Check if the specific permission needs approval in current mode
        for perm in spec.permissions:
            if mode.needs_approval(perm) and not self.auto_approve:
                return ApprovalStatus(
                    granted=False,
                    reason=f"approval_required: {perm} requires approval in {mode.name} mode",
                )

        return ApprovalStatus(granted=True)


class ToolRuntime:
    """Unified tool execution runtime.

    Every tool call goes through:
    SafetyGate -> PermissionPolicy -> ApprovalGate -> PreToolUse Hook -> Handler -> PostToolUse Hook

    LLM cannot call handlers directly.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        permission_mode: str = "read_only",
        safety_gate: SafetyGate | None = None,
        approval_gate: ApprovalGate | None = None,
        pre_hooks: list[Any] | None = None,
        post_hooks: list[Any] | None = None,
        hook_registry: HookRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.permission_mode = permission_mode
        self.safety_gate = safety_gate or SafetyGate()
        self.approval_gate = approval_gate or ApprovalGate(auto_approve=False)
        self.pre_hooks = pre_hooks or []
        self.post_hooks = post_hooks or []
        self.hook_registry = hook_registry

    def run(self, call: ToolCall, context: ToolContext | None = None) -> ToolResult:
        """Execute a tool call through the full safety chain."""
        if context is None:
            context = ToolContext(permission_mode=self.permission_mode)

        # 1. Look up tool spec
        spec = self.registry.get(call.tool_name)
        if spec is None:
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                error=f"tool_not_found: '{call.tool_name}' is not registered",
                risk_level="low",
            )

        # 2. SafetyGate — always enforced, cannot be overridden
        safety = self.safety_gate.check(spec, call, context)
        if not safety.allowed:
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                error=safety.reason,
                risk_level=safety.risk_level,
                metadata={"safety_refusal": True},
            )

        # 3. PermissionPolicy — check if action is allowed in current mode
        mode = get_permission_mode(context.permission_mode)
        for perm in spec.permissions:
            if not mode.allows(perm):
                return ToolResult(
                    tool_name=call.tool_name,
                    ok=False,
                    error=f"permission_denied: {perm} is not allowed in {mode.name} mode",
                    risk_level="medium",
                    metadata={"permission_denied": True, "permission": perm, "mode": mode.name},
                )

        # 4. ApprovalGate
        approval = self.approval_gate.check(spec, call, context)
        if not approval.granted:
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                error=approval.reason,
                risk_level=spec.risk_level,
                requires_approval=True,
                metadata={"approval_required": True},
            )

        # 5. PreToolUse hooks (legacy list-based)
        for hook in self.pre_hooks:
            result = hook(spec, call, context)
            if isinstance(result, HookResult) and not result.allowed:
                return ToolResult(
                    tool_name=call.tool_name,
                    ok=False,
                    error=f"hook_denied: {result.reason or 'pre_tool_use hook denied'}",
                    risk_level=spec.risk_level,
                    metadata={"hook_denied": True},
                )

        # 5b. PreToolUse hooks (HookRegistry)
        if self.hook_registry is not None:
            pre_result = self.hook_registry.run_pre_tool_use(
                tool_name=call.tool_name,
                risk_level=spec.risk_level,
                permission=",".join(sorted(spec.permissions)),
                call=call,
                context=context,
            )
            if not pre_result.allowed:
                return ToolResult(
                    tool_name=call.tool_name,
                    ok=False,
                    error=f"hook_denied: {pre_result.reason or 'pre_tool_use hook denied'}",
                    risk_level=spec.risk_level,
                    metadata={"hook_denied": True},
                )

        # 6. Execute handler
        if spec.handler is None:
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                error=f"no_handler: {spec.name} has no handler",
                risk_level=spec.risk_level,
            )

        try:
            result = spec.handler(call.arguments, context)
        except Exception as exc:
            result = ToolResult(
                tool_name=call.tool_name,
                ok=False,
                error=f"handler_error: {type(exc).__name__}: {exc}",
                risk_level=spec.risk_level,
            )

        # 7. PostToolUse hooks (audit only — cannot modify result)
        for hook in self.post_hooks:
            try:
                hook(spec, call, result, context)
            except Exception:
                pass  # Post hooks are audit-only, errors are swallowed

        # 7b. PostToolUse hooks (HookRegistry)
        if self.hook_registry is not None:
            self.hook_registry.run_post_tool_use(
                tool_name=call.tool_name,
                risk_level=spec.risk_level,
                permission=",".join(sorted(spec.permissions)),
                call=call,
                result=result,
                context=context,
            )

        return result
