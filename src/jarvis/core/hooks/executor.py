from __future__ import annotations

from typing import Any

from ..policy import ApprovalRiskMatrix
from .registry import HookRegistry


class HookExecutor:
    def __init__(self, registry: HookRegistry, risk_matrix: ApprovalRiskMatrix) -> None:
        self.registry = registry
        self.risk_matrix = risk_matrix

    def run(self, hook_point: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for reg in self.registry.get(hook_point):
            decision = self.risk_matrix.evaluate_action(
                tool_name="hook.execute",
                action_input={"hook_point": hook_point, "hook_id": reg.hook_id},
                route_result={"approval_risk_hints": {"approval_required": False}},
            )
            if not decision.get("ok"):
                results.append({"hook_id": reg.hook_id, "ok": False, "error": "risk_matrix_error"})
                continue
            if decision["data"].get("approval_required"):
                results.append({"hook_id": reg.hook_id, "ok": False, "error": "hook_requires_approval"})
                continue
            try:
                out = reg.callback(payload) or {}
                results.append({"hook_id": reg.hook_id, "ok": True, "output": out})
            except Exception as exc:  # pragma: no cover
                results.append({"hook_id": reg.hook_id, "ok": False, "error": str(exc)})
        return results

