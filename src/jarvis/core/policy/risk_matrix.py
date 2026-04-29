"""Approval/risk matrix for runtime action evaluation."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from ..result import ok_result
from ..routing import RoutingConfigManager
from .approval_risk_config import ApprovalRiskConfigManager


class ApprovalRiskMatrix:
    def __init__(self, config_manager: RoutingConfigManager | None = None) -> None:
        self.config_manager = config_manager or RoutingConfigManager()
        self.policy_pack = ApprovalRiskConfigManager()

    def evaluate_action(self, *, tool_name: str, action_input: dict[str, Any], route_result: dict[str, Any] | None = None) -> dict:
        started = perf_counter()
        cfg = self.policy_pack.active or self.config_manager.config.get("approval_risk_config") or {}
        action_map = cfg.get("action_category_map") or {}
        matrix = cfg.get("matrix") or {}
        default_tier = str(cfg.get("default_tier") or "low")
        category = str(action_map.get(tool_name) or "analysis")
        row = dict(matrix.get(category) or {})
        tier = str(row.get("tier") or default_tier)
        decision = str(row.get("approval") or "allow")
        approval_required = decision == "require_confirmation"
        reasons = [f"category:{category}", f"decision:{decision}"]
        route_hints = (route_result or {}).get("approval_risk_hints") or {}
        if isinstance(route_hints, dict) and route_hints.get("approval_required"):
            approval_required = True
            reasons.append("route_hint:approval_required")
            tier = str(route_hints.get("risk_level") or tier)
        command = str(action_input.get("command") or "").strip().lower()
        if command and self._is_safe_local_command(command):
            approval_required = False
            decision = "allow"
            tier = "low" if tier == "high" else tier
            reasons.append("safe_command_allowlist")
        if command and "git push" in command:
            approval_required = True
            tier = "critical"
            reasons.append("command:git_push")
        payload = {
            "risk_tier": tier,
            "risk_category": category,
            "approval_required": approval_required,
            "approval_reason": ";".join(reasons[:4]),
            "escalation_path": "stop_and_ask_user" if approval_required else "continue",
            "policy_source": "routing.approval_risk_config",
            "decision": decision,
        }
        return ok_result(payload, started)

    @staticmethod
    def _is_safe_local_command(command: str) -> bool:
        safe_prefixes = (
            "python ",
            "python.exe ",
            "pytest ",
            "echo ",
            "dir",
            "ls",
            "cat ",
            "type ",
        )
        unsafe_markers = ("rm ", "del ", "rmdir ", "git push", "shutdown", "format ")
        if any(marker in command for marker in unsafe_markers):
            return False
        return any(command.startswith(prefix) for prefix in safe_prefixes)
