"""Lifecycle event bus for session/turn/compact hooks.

Fires hook events at key lifecycle points and aggregates results.
Pre-action hooks (SESSION_START, TURN_START, COMPACT_PRE, PRE_TOOL_USE)
can deny/modify; post-action hooks are audit-only.
"""

from __future__ import annotations

from typing import Any

from .schema import HookResult, HookSpec, HookStage

LIFECYCLE_STAGES = {
    HookStage.SESSION_START,
    HookStage.SESSION_END,
    HookStage.TURN_START,
    HookStage.TURN_END,
    HookStage.COMPACT_PRE,
}


class LifecycleEventBus:
    """Central bus for lifecycle event hooks.

    Hooks are registered as HookSpec instances with a stage and handler.
    When an event fires, all matching hooks run in registration order.
    Pre-action hooks that return ``allowed=False`` block the action.
    """

    def __init__(self) -> None:
        self._specs: list[HookSpec] = []

    def register(self, spec: HookSpec) -> dict[str, Any]:
        """Register a lifecycle hook. Returns status dict."""
        if spec.stage not in LIFECYCLE_STAGES:
            return {"ok": False, "error": f"unknown lifecycle stage: {spec.stage}"}
        self._specs.append(spec)
        return {"ok": True, "data": {"name": spec.name, "stage": spec.stage}}

    def unregister(self, name: str) -> bool:
        """Remove a hook by name. Returns True if found and removed."""
        before = len(self._specs)
        self._specs = [s for s in self._specs if s.name != name]
        return len(self._specs) < before

    def fire(self, stage: HookStage, payload: dict[str, Any] | None = None) -> HookResult:
        """Fire all hooks registered for *stage*.

        Returns the first denial, or ``HookResult(allowed=True)`` if all pass.
        Handlers receive **payload as kwargs.
        """
        ctx = dict(payload or {})
        for spec in self._specs:
            if spec.stage != stage:
                continue
            if spec.handler is None:
                continue
            try:
                result = spec.handler(**ctx)
                if isinstance(result, HookResult) and not result.allowed:
                    return result
                if isinstance(result, dict) and not result.get("allowed", True):
                    return HookResult(
                        allowed=False,
                        reason=str(result.get("reason", "")),
                        message=str(result.get("message", "")),
                        metadata=dict(result.get("metadata") or {}),
                    )
            except Exception as exc:
                return HookResult(
                    allowed=False,
                    reason=f"Hook '{spec.name}' raised {type(exc).__name__}: {exc}",
                )
        return HookResult(allowed=True)

    def fire_audit(self, stage: HookStage, payload: dict[str, Any] | None = None) -> HookResult:
        """Fire hooks for *stage* in audit-only mode. Errors are swallowed."""
        ctx = dict(payload or {})
        for spec in self._specs:
            if spec.stage != stage:
                continue
            if spec.handler is None:
                continue
            try:
                spec.handler(**ctx)
            except Exception:
                pass
        return HookResult(allowed=True)

    def list_hooks(self) -> list[dict[str, Any]]:
        """List all registered hooks with their metadata."""
        return [
            {
                "name": s.name,
                "stage": s.stage,
                "description": s.description,
                "risk_level": s.risk_level,
                "has_handler": s.handler is not None,
            }
            for s in self._specs
        ]

    def snapshot(self) -> dict[str, Any]:
        return {
            "hooks": self.list_hooks(),
            "count": len(self._specs),
        }
