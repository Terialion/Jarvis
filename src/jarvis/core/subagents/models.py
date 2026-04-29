from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubagentRun:
    subagent_id: str
    parent_run_id: str
    task: str
    budget_steps: int = 3
    context: dict[str, Any] = field(default_factory=dict)

