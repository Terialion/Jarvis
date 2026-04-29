"""Shared models for skill harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SkillEntry:
    skill_id: str
    skill_name: str
    source: str
    status: str = "enabled"
    required_tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    priority_hint: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "source": self.source,
            "status": self.status,
            "required_tools": list(self.required_tools),
            "tags": list(self.tags),
            "description": self.description,
            "priority_hint": float(self.priority_hint),
            "metadata": dict(self.metadata),
        }


@dataclass
class SkillMatch:
    skill_id: str
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "score": round(float(self.score), 4),
            "reasons": list(self.reasons),
        }


@dataclass
class SkillHitRecord:
    run_id: str
    task_id: str
    step_number: int
    active_skills: list[str]
    matched_skill_ids: list[str]
    chosen_skill_id: str | None
    chosen_tool: str | None
    action_outcome: str
    usefulness_score: float
    effectiveness_label: str
    seeded_by_policy: bool = False
    seed_sources: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "step_number": self.step_number,
            "active_skills": list(self.active_skills),
            "matched_skill_ids": list(self.matched_skill_ids),
            "chosen_skill_id": self.chosen_skill_id,
            "chosen_tool": self.chosen_tool,
            "action_outcome": self.action_outcome,
            "usefulness_score": round(float(self.usefulness_score), 4),
            "effectiveness_label": self.effectiveness_label,
            "seeded_by_policy": bool(self.seeded_by_policy),
            "seed_sources": list(self.seed_sources),
            "created_at": self.created_at,
        }


@dataclass
class SkillRecord:
    id: str
    name: str
    root: str
    source: str
    description: str = ""
    entrypoint: str | None = None
    triggers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    trust: str = "untrusted"
    quarantine: bool = False
    status: str = "available"
    kind: str = "skill"
    manifest_path: str | None = None
    skill_md_path: str | None = None
    when_to_use: list[str] = field(default_factory=list)
    invocation: str = "auto"
    allowed_tools: list[str] = field(default_factory=list)
    arguments: list[str] = field(default_factory=list)
    dynamic_context: bool = False
    subagent: bool = False
    source_priority: int = 0
    shadowed_by: str | None = None
    body_loaded: bool = False
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "root": self.root,
            "source": self.source,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "triggers": list(self.triggers),
            "tools": list(self.tools),
            "permissions": list(self.permissions),
            "trust": self.trust,
            "quarantine": bool(self.quarantine),
            "status": self.status,
            "kind": self.kind,
            "manifest_path": self.manifest_path,
            "skill_md_path": self.skill_md_path,
            "when_to_use": list(self.when_to_use),
            "invocation": self.invocation,
            "allowed_tools": list(self.allowed_tools),
            "arguments": list(self.arguments),
            "dynamic_context": bool(self.dynamic_context),
            "subagent": bool(self.subagent),
            "source_priority": int(self.source_priority),
            "shadowed_by": self.shadowed_by,
            "body_loaded": bool(self.body_loaded),
            "errors": list(self.errors),
            "metadata": dict(self.metadata),
        }


@dataclass
class SkillSelectionResult:
    input_text: str
    selected: list[SkillRecord] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    dry_run: bool = True
    reason: str = ""
    policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "input_text": self.input_text,
            "selected": [skill.to_dict() for skill in self.selected],
            "rejected": list(self.rejected),
            "dry_run": bool(self.dry_run),
            "reason": self.reason,
            "policy": dict(self.policy),
        }


@dataclass
class SkillExecutionPolicy:
    mode: str = "safe"  # safe | ask | edit
    network_enabled: bool = False
    shell_enabled: bool = False
    file_write_enabled: bool = False
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    approval_required_tools: list[str] = field(default_factory=list)
    sandbox: str = "read_only"  # read_only | workspace_write | unrestricted

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "network_enabled": bool(self.network_enabled),
            "shell_enabled": bool(self.shell_enabled),
            "file_write_enabled": bool(self.file_write_enabled),
            "allowed_tools": list(self.allowed_tools),
            "denied_tools": list(self.denied_tools),
            "approval_required_tools": list(self.approval_required_tools),
            "sandbox": self.sandbox,
        }
