"""SubagentRunner — runs a subagent task in a thread for pool execution."""

from __future__ import annotations

from typing import Any

from .models import SubagentConfig, SubagentRun
from .policy import tool_whitelist_for_type


class SubagentRunner:
    """Runs sub-agent tasks by spawning real AgentLoop instances with restricted tools.

    Designed to be called from SubagentPool's ThreadPoolExecutor workers.
    """

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

    def run(self, config: SubagentConfig) -> dict[str, Any]:
        """Run a subagent from config. Called by SubagentPool in a thread."""
        if not config.task.strip():
            return {
                "agent_id": config.agent_id,
                "status": "failed",
                "error": "Empty task",
                "final_answer": "",
                "steps": 0,
                "total_tokens": 0,
            }

        from ...agent.loop import AgentLoop
        from ...agent.types import ChatInput

        allowed_tools = tool_whitelist_for_type(config.agent_type)

        loop = AgentLoop(
            project_root=self.project_root,
            model_client=self.model_client,
            tool_registry=self.tool_registry,
            max_steps=min(max(1, config.budget_steps), 20),
            allowed_tools=allowed_tools,
            subagent_depth=config.depth,
        )
        result = loop.run_turn(
            ChatInput(
                text=config.task,
                cwd=self.project_root,
                project_id=config.parent_run_id or "",
                session_id=f"subagent_{config.agent_id}",
            )
        )
        return {
            "agent_id": config.agent_id,
            "status": "completed" if result.ok else "failed",
            "final_answer": result.final_answer,
            "summary": result.summary.get("human", result.final_answer),
            "steps": result.step_count if hasattr(result, "step_count") else 0,
            "total_tokens": result.total_tokens if hasattr(result, "total_tokens") else 0,
        }

    # Legacy compat — wraps run() for old SubagentRun callers
    def run_subtask(self, run: SubagentRun) -> dict[str, Any]:
        config = SubagentConfig(
            agent_id=run.subagent_id,
            agent_type="general-purpose",
            task=run.task,
            parent_run_id=run.parent_run_id,
            budget_steps=run.budget_steps,
            depth=0,
            context=run.context,
        )
        result = self.run(config)
        return {
            "subagent_id": result["agent_id"],
            "parent_run_id": run.parent_run_id,
            "status": result["status"],
            "error": result.get("error"),
            "trace": [],
            "result": {
                "final_answer": result["final_answer"],
                "summary": result.get("summary", result["final_answer"]),
                "confidence": 0.8 if result["status"] == "completed" else 0.0,
            },
        }
