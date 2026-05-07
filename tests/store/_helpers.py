from __future__ import annotations

from src.jarvis.agent.skill_context import ActiveTaskState, HandoffSummary, SkillObservation
from src.jarvis.agent.types import AgentRunResult
from src.jarvis.web.research_context import ResearchObservation


def make_agent_result(*, session_id: str = "thread_test", turn_id: str = "turn_test", final_answer: str = "done") -> AgentRunResult:
    return AgentRunResult(
        ok=True,
        session_id=session_id,
        turn_id=turn_id,
        final_answer=final_answer,
        events=[],
        summary={"human": final_answer, "machine": {}},
        stop_reason="completed",
        tool_calls=[],
        tool_results=[],
        status="completed",
        output_type="answer",
        available_skills=[],
        loaded_skills=[],
        skill_loads_count=0,
        skills_used=["repo_overview"],
        skill_calls_count=0,
        skill_results=[],
        model_backend="fake",
        model_provider="fake",
        model_name="fake-agent-v0",
    )


def make_skill_observation(summary: str = "Observed repository") -> SkillObservation:
    return SkillObservation(
        skill_name="repo_overview",
        summary=summary,
        facts={"kind": "repo"},
        related_files=["README.md"],
        tool_calls=["repo_overview"],
    )


def make_research_observation(summary: str = "Observed research") -> ResearchObservation:
    return ResearchObservation(
        query="phase 17 persistence",
        search_tasks=[{"query": "phase 17"}],
        sources=[{"url": "https://example.com", "title": "Example"}],
        evidence=[{"quote": "example evidence", "source": "https://example.com"}],
        answer_summary=summary,
        confidence=0.7,
        remaining_questions=["none"],
    )


def make_active_task() -> ActiveTaskState:
    task = ActiveTaskState.new(user_goal="Finish Phase 17", current_phase="implementation")
    task.remaining_work = ["run tests"]
    task.related_files = ["src/jarvis/store/thread_store.py"]
    task.skills_used = ["repo_overview"]
    return task


def make_handoff() -> HandoffSummary:
    return HandoffSummary(
        user_goal="Finish Phase 17",
        current_state="Persistent state saved",
        completed_work=["implemented thread store"],
        remaining_work=["run tests"],
        context_to_keep=["thread store"],
        risks=["secret persistence"],
    )
