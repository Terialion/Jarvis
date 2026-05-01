from __future__ import annotations

from pathlib import Path
from time import time
from typing import Any

from src.jarvis.core.instructions import load_project_instructions
from src.jarvis.core.llm.provider import LLMProvider
from src.jarvis.core.recommendations import recommend_next_actions

from .loop import run_coding_loop_for_fixture
from .review import build_final_review


class CodingLoopOrchestrator:
    def __init__(self, *, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def run_coding_loop(
        self,
        user_goal: str,
        workspace_root: Path,
        *,
        max_rounds: int = 3,
        auto_approve: bool = False,
        force_first_failure: bool = False,
    ) -> dict[str, Any]:
        root = workspace_root.resolve()
        instructions = load_project_instructions(root)
        task_id = f"coding_{int(time() * 1000)}"
        target = root / "examples" / "coding_fixture" / "greeting.py"

        if not auto_approve:
            result = {
                "task_id": task_id,
                "status": "approval_required",
                "stop_reason": "approval_required",
                "rounds": 0,
                "changed_files": [],
                "approvals": [
                    {
                        "round": 0,
                        "kind": "write_and_shell",
                        "status": "pending",
                        "reason": "Coding tasks require approval before file writes or scoped tests.",
                    }
                ],
                "diffs": [],
                "test_results": [],
                "rethink_records": [],
                "instruction_sources": [source.__dict__ for source in instructions.sources],
                "risk_level": "medium",
                "trace_path": str(root / "temp" / "coding_loop" / "smoke_runs.jsonl"),
            }
            result["next_suggestions"] = [item.__dict__ for item in recommend_next_actions({"stop_reason": "approval_required"})]
            result["final_review"] = build_final_review(result)
            return result

        if not target.exists():
            result = {
                "task_id": task_id,
                "status": "user_needed",
                "stop_reason": "user_needed",
                "rounds": 0,
                "changed_files": [],
                "approvals": [],
                "diffs": [],
                "test_results": [],
                "rethink_records": [],
                "instruction_sources": [source.__dict__ for source in instructions.sources],
                "risk_level": "low",
                "trace_path": str(root / "temp" / "coding_loop" / "smoke_runs.jsonl"),
                "next_suggestions": [{"label": "Provide a concrete target", "reason": "The controlled greeting fixture was not found.", "priority": "high"}],
            }
            result["final_review"] = build_final_review(result)
            return result

        result = run_coding_loop_for_fixture(
            workspace_root=root,
            task_id=task_id,
            user_goal=user_goal,
            max_rounds=max_rounds,
            auto_approve=auto_approve,
            force_first_failure=force_first_failure,
            instructions=instructions,
            llm_provider=self.llm_provider,
        )
        result["changed_files"] = ["examples/coding_fixture/greeting.py"] if result.get("diffs") else []
        result["risk_level"] = "medium"
        result["next_suggestions"] = [item.__dict__ for item in recommend_next_actions({"stop_reason": result.get("stop_reason")})]
        result["final_review"] = build_final_review(result)
        return result


def run_coding_loop(
    user_goal: str,
    workspace_root: Path,
    *,
    max_rounds: int = 3,
    auto_approve: bool = False,
    force_first_failure: bool = False,
    llm_provider: LLMProvider | None = None,
) -> dict[str, Any]:
    return CodingLoopOrchestrator(llm_provider=llm_provider).run_coding_loop(
        user_goal,
        workspace_root,
        max_rounds=max_rounds,
        auto_approve=auto_approve,
        force_first_failure=force_first_failure,
    )

