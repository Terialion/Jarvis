from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Observation:
    round: int
    type: str
    ok: bool
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class LoopDecision:
    decision: str
    success: bool
    confidence: float
    stop_reason: str
    why: str
    next_plan: list[str] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    requires_approval: bool = False
    risk_level: str = "low"


@dataclass
class RethinkRecord:
    round: int
    trigger: str
    previous_plan: list[str]
    observation_summary: str
    diagnosis: str
    revised_plan: list[str]
    learning_signal: str = "none"


@dataclass
class CodingLoopState:
    task_id: str
    workspace_root: str
    user_goal: str
    current_plan: list[str] = field(default_factory=list)
    round: int = 0
    max_rounds: int = 3
    observations: list[Observation] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)
    approvals: list[dict[str, Any]] = field(default_factory=list)
    diffs: list[dict[str, Any]] = field(default_factory=list)
    test_results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "planning"
    stop_reason: str | None = None
    rethink_records: list[RethinkRecord] = field(default_factory=list)

