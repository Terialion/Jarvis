from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RETHINK_TRIGGERS = {
    "test_failed",
    "tool_failed",
    "low_route_confidence",
    "no_progress",
    "repeated_failure",
    "evidence_insufficient",
    "approval_denied",
    "subagent_failed",
    "memory_conflict",
    "policy_blocked",
}


@dataclass
class RethinkTrigger:
    trigger: str
    reason: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyAdjustment:
    strategy: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillAdjustment:
    add: list[str] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class RevisedPlan:
    plan_actions: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""


@dataclass
class RethinkDecision:
    should_rethink: bool
    trigger: str
    confidence: float
    reason: str


@dataclass
class RethinkResult:
    decision: RethinkDecision
    revised_plan: RevisedPlan
    strategy_adjustment: StrategyAdjustment
    skill_adjustment: SkillAdjustment
