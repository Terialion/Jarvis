from __future__ import annotations

from typing import Any

from .models import SubagentRun


class SubagentRunner:
    """Runs sub-agent tasks by spawning real AgentLoop instances."""

    def __init__(
        self,
        *,
        project_root: str = ".",
        model_client: Any = None,
        tool_registry: Any = None,
    ) -> None:
        self.project_root = project_root
        self.model_client = model_client
        self.tool_registry = tool_registry

    def run_subtask(self, run: SubagentRun) -> dict[str, Any]:
        if not run.task.strip():
            return {
                "subagent_id": run.subagent_id,
                "parent_run_id": run.parent_run_id,
                "status": "failed",
                "error": "task.delegate requires a non-empty task description.",
                "trace": [],
                "result": {"summary": "No task provided.", "confidence": 0.0},
            }

        from ...agent.loop import AgentLoop
        from ...agent.types import ChatInput

        loop = AgentLoop(
            project_root=self.project_root,
            model_client=self.model_client,
            tool_registry=self.tool_registry,
            auto_approve=True,
            max_steps=min(max(1, run.budget_steps), 20),
        )
        result = loop.run_turn(
            ChatInput(
                text=run.task,
                cwd=self.project_root,
                project_id=run.parent_run_id or "",
                session_id=f"subagent_{run.subagent_id}",
            )
        )
        return {
            "subagent_id": run.subagent_id,
            "parent_run_id": run.parent_run_id,
            "status": "completed" if result.ok else "failed",
            "trace": result.events,
            "result": {
                "final_answer": result.final_answer,
                "summary": result.summary.get("human", result.final_answer),
                "confidence": 0.8 if result.ok else 0.0,
            },
        }
