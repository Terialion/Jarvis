"""Deterministic skill selection for task input."""

from __future__ import annotations

import re
from typing import Any

from .instructions import ProjectInstructionContext, load_project_instruction_context
from .models import SkillRecord, SkillSelectionResult
from .registry import SkillRegistry


def _extract_manual_skill_requests(input_text: str) -> set[str]:
    text = input_text or ""
    requested: set[str] = set()
    for token in re.findall(r"/([a-zA-Z0-9_.-]+)", text):
        requested.add(token.lower())
    for token in re.findall(r"\bskill[:\s]+([a-zA-Z0-9_.-]+)\b", text, flags=re.IGNORECASE):
        requested.add(token.lower())
    return requested


def _build_instruction_context(policy: dict[str, Any]) -> ProjectInstructionContext:
    explicit = policy.get("instruction_context")
    if isinstance(explicit, ProjectInstructionContext):
        return explicit
    project_root = policy.get("project_root")
    return load_project_instruction_context(project_root)


def select_skills_for_task(input_text: str, registry: SkillRegistry, policy: dict | None = None) -> SkillSelectionResult:
    effective_policy: dict[str, Any] = {
        "safe_mode": True,
        "network_enabled": False,
        "require_approval_for_untrusted": True,
        "allowlist": [],
        "denylist": [],
        "mode": "safe",
        "file_write_enabled": False,
        "shell_enabled": False,
        "allowed_tools": [],
        "denied_tools": [],
    }
    effective_policy.update(dict(policy or {}))
    query = (input_text or "").strip().lower()
    requested_manual = _extract_manual_skill_requests(input_text or "")
    instruction_context = _build_instruction_context(effective_policy)

    selected: list[SkillRecord] = []
    rejected: list[dict[str, Any]] = []
    for record in registry.list_skill_records(include_invalid=True):
        reasons: list[str] = []
        score = 0
        if record.status in {"invalid", "quarantined", "disabled", "shadowed"}:
            rejected.append({"skill_id": record.id, "reason": record.status})
            continue
        if record.quarantine:
            rejected.append({"skill_id": record.id, "reason": "quarantined"})
            continue
        if record.id in set(effective_policy.get("denylist") or []):
            rejected.append({"skill_id": record.id, "reason": "denylist"})
            continue
        allowlist = list(effective_policy.get("allowlist") or [])
        if allowlist and record.id not in allowlist:
            rejected.append({"skill_id": record.id, "reason": "not_in_allowlist"})
            continue
        if record.id.lower() in {item.lower() for item in instruction_context.blocked_skills}:
            rejected.append({"skill_id": record.id, "reason": "blocked_by_project_instruction"})
            continue
        if record.invocation == "disabled":
            rejected.append({"skill_id": record.id, "reason": "invocation_disabled"})
            continue
        if record.invocation == "manual":
            if record.id.lower() not in requested_manual and record.name.lower() not in requested_manual:
                rejected.append({"skill_id": record.id, "reason": "manual_invocation_required"})
                continue
            score += 3
            reasons.append("manual_invocation")
        for trigger in record.triggers:
            trigger_low = trigger.lower()
            if trigger_low and trigger_low in query:
                score += 4
                reasons.append(f"trigger:{trigger}")
        for clue in record.when_to_use:
            clue_low = clue.lower()
            if clue_low and clue_low in query:
                score += 2
                reasons.append(f"when_to_use:{clue}")
        if record.name.lower() in query:
            score += 3
            reasons.append("name_match")
        if record.id.lower() in query:
            score += 3
            reasons.append("id_match")
        for token in (record.description or "").lower().split():
            if len(token) >= 4 and token in query:
                score += 1
                reasons.append(f"description:{token}")
                break
        if not effective_policy.get("network_enabled", False) or instruction_context.no_network:
            if any("network" in permission.lower() for permission in record.permissions):
                rejected.append({"skill_id": record.id, "reason": "network_disabled"})
                continue
        if effective_policy.get("require_approval_for_untrusted", True):
            if record.trust in {"untrusted", "unknown", "imported-reference", "needs_review"}:
                rejected.append({"skill_id": record.id, "reason": "approval_required_for_untrusted"})
                continue
        preferred = {item.lower() for item in instruction_context.preferred_skills}
        if record.id.lower() in preferred or record.name.lower() in preferred:
            score += 3
            reasons.append("preferred_by_project_instruction")
        denied_tools = {str(t).lower() for t in list(effective_policy.get("denied_tools") or [])}
        if denied_tools and any(tool.lower() in denied_tools for tool in list(record.tools) + list(record.allowed_tools)):
            rejected.append({"skill_id": record.id, "reason": "denied_tool_by_policy"})
            continue
        if score > 0:
            enriched = SkillRecord(**record.to_dict())
            enriched.metadata = {**record.metadata, "selection_score": score, "selection_reasons": reasons}
            selected.append(enriched)

    selected.sort(key=lambda item: (-int(item.metadata.get("selection_score", 0)), -int(item.source_priority), item.id))

    reason = "no_match"
    if selected:
        reason = "matched_triggers"
    effective_policy["instruction_context"] = instruction_context.to_dict()
    return SkillSelectionResult(
        input_text=input_text,
        selected=selected,
        rejected=rejected,
        dry_run=bool(effective_policy.get("safe_mode", True)),
        reason=reason,
        policy=effective_policy,
    )
