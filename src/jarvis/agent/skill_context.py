"""Context records produced by executable skill runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SkillObservation:
    skill_name: str
    summary: str
    facts: dict[str, Any] = field(default_factory=dict)
    related_files: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActiveTaskState:
    task_id: str
    user_goal: str
    current_phase: str
    completed_steps: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    @classmethod
    def new(cls, *, user_goal: str, current_phase: str = "in_progress") -> "ActiveTaskState":
        return cls(task_id=f"task_{uuid4().hex[:12]}", user_goal=user_goal, current_phase=current_phase)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HandoffSummary:
    user_goal: str
    current_state: str
    completed_work: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    context_to_keep: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
