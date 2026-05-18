"""Task planning models for Gap 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .manager import PersistentTaskManager

__all__ = ["TaskPlan", "TaskPlanStep", "PersistentTaskManager"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskPlanStep:
    step_id: str
    description: str
    status: str = "pending"  # pending | in_progress | completed | failed
    depends_on: list[str] = field(default_factory=list)
    estimated_tool: str | None = None
    result: str | None = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "status": self.status,
            "depends_on": list(self.depends_on),
            "estimated_tool": self.estimated_tool,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TaskPlanStep:
        return cls(
            step_id=str(d.get("step_id") or ""),
            description=str(d.get("description") or ""),
            status=str(d.get("status") or "pending"),
            depends_on=list(d.get("depends_on") or []),
            estimated_tool=d.get("estimated_tool"),
            result=d.get("result"),
        )


@dataclass
class TaskPlan:
    plan_id: str
    session_id: str
    goal: str
    steps: list[TaskPlanStep] = field(default_factory=list)
    status: str = "active"  # active | completed | abandoned
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    metadata: dict = field(default_factory=dict)

    @classmethod
    def new(cls, session_id: str, goal: str, steps: list[dict | str]) -> TaskPlan:
        plan_steps = [
            TaskPlanStep(
                step_id=f"step_{i + 1}",
                description=str(s.get("description")) if isinstance(s, dict) else str(s),
                depends_on=list(s.get("depends_on") or []) if isinstance(s, dict) else [],
                estimated_tool=s.get("estimated_tool") if isinstance(s, dict) else None,
            )
            for i, s in enumerate(steps)
        ]
        return cls(
            plan_id=f"plan_{uuid4().hex[:10]}",
            session_id=session_id,
            goal=goal,
            steps=plan_steps,
        )

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict) -> TaskPlan:
        steps = [TaskPlanStep.from_dict(s) for s in (d.get("steps") or [])]
        return cls(
            plan_id=str(d.get("plan_id") or ""),
            session_id=str(d.get("session_id") or ""),
            goal=str(d.get("goal") or ""),
            steps=steps,
            status=str(d.get("status") or "active"),
            created_at=str(d.get("created_at") or _utc_now()),
            updated_at=str(d.get("updated_at") or _utc_now()),
            metadata=dict(d.get("metadata") or {}),
        )
