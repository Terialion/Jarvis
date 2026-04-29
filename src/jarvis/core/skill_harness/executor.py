"""Safe skill execution adapter (dry-run first)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import SkillExecutionPolicy
from .registry import SkillRegistry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def execute_skill(
    skill_id: str,
    input_text: str,
    *,
    registry: SkillRegistry,
    dry_run: bool = True,
    policy: dict | None = None,
) -> dict[str, Any]:
    raw_policy = dict(policy or {})
    normalized_policy = SkillExecutionPolicy(
        mode=str(raw_policy.get("mode") or "safe"),
        network_enabled=bool(raw_policy.get("network_enabled", False)),
        shell_enabled=bool(raw_policy.get("shell_enabled", False)),
        file_write_enabled=bool(raw_policy.get("file_write_enabled", False)),
        allowed_tools=list(raw_policy.get("allowed_tools") or []),
        denied_tools=list(raw_policy.get("denied_tools") or []),
        approval_required_tools=list(raw_policy.get("approval_required_tools") or []),
        sandbox=str(raw_policy.get("sandbox") or ("read_only" if str(raw_policy.get("mode") or "safe") == "safe" else "workspace_write")),
    )
    record_res = registry.get_skill(skill_id)
    if not record_res.get("ok"):
        return {
            "skill_id": skill_id,
            "status": "failed",
            "reason": "skill_not_found",
            "requires_approval": False,
            "policy_check": {
                "allowed": False,
                "blocked": True,
                "approval_required": False,
                "dry_run": True,
                "reason": "skill_not_found",
            },
            "evidence": [],
        }
    record = record_res["data"]
    denied = {str(item).lower() for item in normalized_policy.denied_tools}
    tools = [str(item).lower() for item in list(record.get("required_tools") or record.get("tools") or [])]
    permissions = [str(item).lower() for item in list(record.get("permissions") or [])]
    trust = str(record.get("trust") or "").lower()
    requires_approval = bool(
        record.get("quarantine")
        or trust in {"untrusted", "unknown", "imported-reference", "needs_review"}
        or any(tool in {item.lower() for item in normalized_policy.approval_required_tools} for tool in tools)
    )
    blocked_reason = ""
    if str(record.get("status") or "").lower() in {"invalid", "disabled", "quarantined", "shadowed"}:
        blocked_reason = f"status_blocked:{record.get('status')}"
    elif any(tool in denied for tool in tools):
        blocked_reason = "denied_tool"
    elif any("network" in permission for permission in permissions) and not normalized_policy.network_enabled:
        blocked_reason = "network_disabled"
    elif any("shell" in permission for permission in permissions) and not normalized_policy.shell_enabled:
        blocked_reason = "shell_disabled"
    elif any("write" in permission for permission in permissions) and not normalized_policy.file_write_enabled:
        blocked_reason = "file_write_disabled"

    if blocked_reason:
        return {
            "skill_id": skill_id,
            "status": "blocked",
            "reason": blocked_reason,
            "requires_approval": False,
            "policy": normalized_policy.to_dict(),
            "policy_check": {
                "allowed": False,
                "blocked": True,
                "approval_required": False,
                "dry_run": True,
                "reason": blocked_reason,
            },
            "evidence": [
                {"kind": "skill_selection", "detail": skill_id},
                {"kind": "skill_policy", "detail": {"blocked_reason": blocked_reason}},
            ],
            "ts": _now(),
        }

    if not dry_run and requires_approval:
        return {
            "skill_id": skill_id,
            "status": "blocked",
            "reason": "approval_required",
            "requires_approval": True,
            "policy": normalized_policy.to_dict(),
            "policy_check": {
                "allowed": False,
                "blocked": False,
                "approval_required": True,
                "dry_run": False,
                "reason": "approval_required",
            },
            "evidence": [{"kind": "policy", "detail": "untrusted_or_quarantined"}],
            "ts": _now(),
        }
    return {
        "skill_id": skill_id,
        "status": "dry_run" if dry_run else "executed",
        "would_execute": f"skill={skill_id} input={input_text[:160]}",
        "requires_approval": requires_approval,
        "policy": normalized_policy.to_dict(),
        "policy_check": {
            "allowed": True,
            "blocked": False,
            "approval_required": requires_approval,
            "dry_run": bool(dry_run),
            "reason": "allowed_dry_run" if dry_run else "allowed_execute",
        },
        "evidence": [
            {"kind": "skill_selection", "detail": skill_id},
            {"kind": "skill_policy", "detail": {"requires_approval": requires_approval}},
            {"kind": "skill_execution", "detail": "dry_run_only" if dry_run else "safe_path"},
        ],
        "ts": _now(),
    }
