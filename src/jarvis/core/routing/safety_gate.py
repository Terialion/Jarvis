"""Safety/approval gate for intent routes."""

from __future__ import annotations

from .schema import IntentRoute, ResponseMode, RiskLevel, SafetyDecision

_SENSITIVE_HINTS = [
    ".env",
    ".npmrc",
    ".ssh",
    "id_rsa",
    "id_ed25519",
    "credential",
    "api token", "access token", "bearer token", "auth token",
    "client secret", "api secret", "secret key",
    "private key",
    "api key",
    "password",
]
_DESTRUCTIVE_HINTS = ["删除整个项目", "delete entire project", "delete the project", "rm -rf", "del /s"]


def apply_route_safety(route: IntentRoute, user_input: str) -> IntentRoute:
    low = str(user_input or "").lower()
    updated = route.to_dict()
    reasons: list[str] = []

    if any(token in low for token in _SENSITIVE_HINTS):
        updated["intent"] = "unknown"
        updated["response_mode"] = ResponseMode.REFUSAL_OR_SAFETY_MESSAGE.value
        updated["risk_level"] = RiskLevel.HIGH.value
        updated["requires_approval"] = True
        updated["summary"] = "sensitive read request"
        reasons.append("sensitive_read_detected")

    if any(token in low for token in _DESTRUCTIVE_HINTS):
        updated["intent"] = "unknown"
        updated["response_mode"] = ResponseMode.REFUSAL_OR_SAFETY_MESSAGE.value
        updated["risk_level"] = RiskLevel.HIGH.value
        updated["requires_write"] = True
        updated["requires_approval"] = True
        updated["summary"] = "destructive request blocked"
        reasons.append("destructive_request_detected")

    if _looks_like_dangerous_shell(low):
        updated["intent"] = "unknown"
        updated["response_mode"] = ResponseMode.REFUSAL_OR_SAFETY_MESSAGE.value
        updated["risk_level"] = RiskLevel.CRITICAL.value
        updated["requires_shell"] = True
        updated["requires_network"] = True
        updated["requires_approval"] = True
        updated["summary"] = "dangerous shell pipeline blocked"
        reasons.append("dangerous_shell_detected")

    if updated.get("requires_write") or updated.get("requires_shell"):
        updated["requires_approval"] = True
    if updated.get("requires_network"):
        updated["requires_approval"] = True
        reasons.append("network_requires_approval")

    updated["safety_decision"] = SafetyDecision(
        requires_approval=bool(updated.get("requires_approval")),
        reasons=reasons,
    ).__dict__
    return IntentRoute(**updated)


def _looks_like_dangerous_shell(low: str) -> bool:
    if ("curl " in low or "wget " in low) and ("| sh" in low or "| bash" in low):
        return True
    if "invoke-webrequest" in low and ("| iex" in low or "invoke-expression" in low):
        return True
    return False
