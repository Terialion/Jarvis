from __future__ import annotations

from typing import Any

from .models import SubagentRun


class SubagentRunner:
    def run_subtask(self, run: SubagentRun) -> dict[str, Any]:
        steps = min(max(1, run.budget_steps), 20)
        trace = [{"step": i + 1, "note": f"subagent step {i + 1}"} for i in range(steps)]
        return {
            "subagent_id": run.subagent_id,
            "parent_run_id": run.parent_run_id,
            "status": "completed",
            "trace": trace,
            "result": {"summary": f"completed subtask: {run.task}", "confidence": 0.6},
        }

