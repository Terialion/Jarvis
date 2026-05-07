"""Runtime contracts for executable Jarvis skills."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from ..agent.types import AgentEvent, TurnContext
from .schema import SkillSpec

SkillCallSource = Literal["model", "deterministic", "slash_command", "benchmark"]
SkillStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SkillCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    source: SkillCallSource = "model"

    @classmethod
    def new(cls, *, name: str, arguments: dict[str, Any] | None = None, source: SkillCallSource = "model") -> "SkillCall":
        return cls(id=f"skill_call_{uuid4().hex[:12]}", name=name, arguments=dict(arguments or {}), source=source)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillStep:
    name: str
    description: str
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    status: SkillStepStatus = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillExecutionContext:
    skill_call: SkillCall
    skill_spec: SkillSpec
    turn_context: TurnContext
    allowed_tools: list[str]
    policy_context: dict[str, Any] = field(default_factory=dict)
    observations: list[dict[str, Any]] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["events"] = [event.to_dict() for event in self.events]
        return data


@dataclass
class SkillResult:
    ok: bool
    skill_name: str
    final_answer: str
    output_type: str
    steps: list[SkillStep] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "skill_name": self.skill_name,
            "final_answer": self.final_answer,
            "output_type": self.output_type,
            "steps": [step.to_dict() for step in self.steps],
            "observations": list(self.observations),
            "tool_calls": list(self.tool_calls),
            "tool_results": list(self.tool_results),
            "events": [event.to_dict() for event in self.events],
            "risks": list(self.risks),
            "related_files": list(self.related_files),
            "created_at": self.created_at,
        }
