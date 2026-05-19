from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SubagentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentConfig:
    agent_id: str
    agent_type: str  # "Explore" | "Plan" | "general-purpose"
    task: str
    parent_run_id: str = ""
    budget_steps: int = 10
    depth: int = 0
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubagentHandle:
    agent_id: str
    agent_type: str
    status: SubagentStatus = SubagentStatus.PENDING
    steps: int = 0
    max_steps: int = 10
    total_tokens: int = 0
    result: str = ""
    error: str = ""
    depth: int = 0


@dataclass
class SubagentRun:
    subagent_id: str
    parent_run_id: str
    task: str
    budget_steps: int = 3
    context: dict[str, Any] = field(default_factory=dict)

