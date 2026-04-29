from __future__ import annotations

from typing import Any

from .models import RETHINK_TRIGGERS


def should_rethink(context: dict[str, Any]) -> bool:
    trigger = classify_rethink_trigger(context)
    return trigger in RETHINK_TRIGGERS


def classify_rethink_trigger(context: dict[str, Any]) -> str:
    if bool(context.get("test_failed")):
        return "test_failed"
    if bool(context.get("tool_failed")):
        return "tool_failed"
    if float(context.get("route_confidence") or 1.0) < 0.55:
        return "low_route_confidence"
    if bool(context.get("no_progress")):
        return "no_progress"
    if int(context.get("repeated_failure_count") or 0) >= 2:
        return "repeated_failure"
    if bool(context.get("evidence_insufficient")):
        return "evidence_insufficient"
    if bool(context.get("approval_denied")):
        return "approval_denied"
    if bool(context.get("subagent_failed")):
        return "subagent_failed"
    if bool(context.get("memory_conflict")):
        return "memory_conflict"
    if bool(context.get("policy_blocked")):
        return "policy_blocked"
    return "none"


def build_rethink_context(**kwargs: Any) -> dict[str, Any]:
    return dict(kwargs)
