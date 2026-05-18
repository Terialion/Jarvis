"""SkillUsePlan — unified planning model for all skill invocation paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PlanSource = Literal["explicit_invocation", "description_match", "slash_command", "followup"]
PlanPath = Literal["skill_run", "reference_guided_tool_call", "ask_clarification", "blocked"]
SkillTypeHint = Literal["executable", "reference", "hybrid", "unknown"]


@dataclass
class SkillUsePlan:
    plan_id: str
    source: PlanSource
    selected_skill: str
    skill_type: SkillTypeHint
    user_goal: str
    extracted_arguments: dict[str, Any] = field(default_factory=dict)
    intended_path: PlanPath = "skill_run"
    tool_calls_preview: list[dict[str, Any]] = field(default_factory=list)
    requires_approval: bool = False
    reason: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "source": self.source,
            "selected_skill": self.selected_skill,
            "skill_type": self.skill_type,
            "user_goal": self.user_goal,
            "extracted_arguments": self.extracted_arguments,
            "intended_path": self.intended_path,
            "tool_calls_preview": self.tool_calls_preview,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "confidence": self.confidence,
        }

    @property
    def is_blocked(self) -> bool:
        return self.intended_path == "blocked"

    @property
    def needs_clarification(self) -> bool:
        return self.intended_path == "ask_clarification"


@dataclass
class SkillAmbiguousMatch:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    user_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "reason": self.reason,
            "user_text": self.user_text,
        }
