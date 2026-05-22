"""HookRegistry — independent registry for pre/post tool use hooks.

Key rules:
- Hooks cannot expand permissions.
- Hooks cannot cancel safety refusal.
- Hooks cannot let shell.run / patch.apply bypass approval.
- PreToolUse allowed=False blocks tool execution.
- PostToolUse is audit-only; errors do not affect ToolResult.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import HOOK_POINTS, HookRegistration
from .schema import HookResult, HookSpec, HookStage


class HookRegistry:
    """Independent registry for lifecycle and tool hooks.

    Supports both the original HookRegistration model and the new HookSpec model.
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookRegistration]] = defaultdict(list)
        self._specs: list[HookSpec] = []

    def register(self, reg: HookRegistration) -> dict[str, Any]:
        if reg.hook_point not in HOOK_POINTS:
            return {"ok": False, "error": {"code": "HOOK_INVALID_POINT", "message": reg.hook_point}}
        self._hooks[reg.hook_point].append(reg)
        return {"ok": True, "data": {"hook_id": reg.hook_id, "hook_point": reg.hook_point}}

    def register_spec(self, spec: HookSpec) -> dict[str, Any]:
        """Register a HookSpec (new-style hook with matcher)."""
        self._specs.append(spec)
        return {"ok": True, "data": {"name": spec.name, "stage": spec.stage}}

    def get(self, hook_point: str) -> list[HookRegistration]:
        return list(self._hooks.get(hook_point, []))

    def list_specs(self) -> list[HookSpec]:
        """List all registered HookSpecs."""
        return list(self._specs)

    def get_pre_tool_hooks(self, *, tool_name: str = "", risk_level: str = "", permission: str = "") -> list[HookSpec]:
        """Get matching pre_tool_use hooks for a tool call."""
        return [
            spec for spec in self._specs
            if spec.stage == "pre_tool_use" and spec.matches(
                tool_name=tool_name, risk_level=risk_level, permission=permission
            )
        ]

    def get_post_tool_hooks(self, *, tool_name: str = "", risk_level: str = "", permission: str = "") -> list[HookSpec]:
        """Get matching post_tool_use hooks for a tool call."""
        return [
            spec for spec in self._specs
            if spec.stage == "post_tool_use" and spec.matches(
                tool_name=tool_name, risk_level=risk_level, permission=permission
            )
        ]

    def run_pre_tool_use(
        self, *, tool_name: str = "", risk_level: str = "", permission: str = "",
        call: Any = None, context: Any = None,
    ) -> HookResult:
        """Run all matching pre_tool_use hooks. Returns first denial."""
        matching = self.get_pre_tool_hooks(
            tool_name=tool_name, risk_level=risk_level, permission=permission,
        )
        for spec in matching:
            if spec.handler is None:
                continue
            try:
                result = spec.handler(call=call, context=context)
                if isinstance(result, HookResult) and not result.allowed:
                    return result
            except Exception as exc:
                # Pre hooks that throw are treated as denial
                return HookResult(
                    allowed=False,
                    reason=f"pre_tool_use hook '{spec.name}' raised {type(exc).__name__}: {exc}",
                )
        return HookResult(allowed=True)

    def run_post_tool_use(
        self, *, tool_name: str = "", risk_level: str = "", permission: str = "",
        call: Any = None, result: Any = None, context: Any = None,
    ) -> HookResult:
        """Run all matching post_tool_use hooks. Audit only — errors swallowed."""
        matching = self.get_post_tool_hooks(
            tool_name=tool_name, risk_level=risk_level, permission=permission,
        )
        for spec in matching:
            if spec.handler is None:
                continue
            try:
                spec.handler(call=call, result=result, context=context)
            except Exception:
                pass  # Post hooks are audit-only, errors are swallowed
        return HookResult(allowed=True)

    def snapshot(self) -> dict[str, Any]:
        return {p: [h.hook_id for h in self._hooks.get(p, [])] for p in HOOK_POINTS}


class HookStageRegistry:
    """No-op stage registry scaffold for future Claude/Hermes-style lifecycle hooks."""

    def __init__(self) -> None:
        self._callbacks: dict[HookStage, list[Any]] = defaultdict(list)

    def register(self, stage: HookStage, callback: Any) -> None:
        self._callbacks[stage].append(callback)

    def run(self, stage: HookStage, payload: dict[str, Any] | None = None) -> HookResult:
        _ = payload or {}
        for callback in self._callbacks.get(stage, []):
            result = callback(payload or {})
            if isinstance(result, HookResult) and not result.allowed:
                return result
        return HookResult()
