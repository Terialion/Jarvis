from __future__ import annotations

from src.jarvis.agent.types import AgentRunResult
from src.jarvis.cli_agent_output import render_agent_result


def test_cli_trace_renders_skill_runtime_events():
    result = AgentRunResult(
        ok=True,
        session_id="s",
        turn_id="t",
        final_answer="Summary complete.",
        events=[
            {"type": "skill_call_started", "payload": {"skill_name": "summarize_file"}},
            {"type": "skill_step_started", "payload": {"step_name": "read_file"}},
            {"type": "tool_call_started", "payload": {"tool_call": {"name": "repo_reader.read_file"}}},
            {"type": "skill_call_completed", "payload": {"skill_name": "summarize_file", "ok": True}},
            {"type": "context_updated", "payload": {"session_id": "s"}},
        ],
        summary={
            "machine": {
                "skills_used": ["summarize_file"],
                "skill_calls_count": 1,
                "active_task": {"current_phase": "completed"},
                "handoff_summary": {"current_state": "summarized README"},
            }
        },
        stop_reason="completed",
        output_type="tool_result",
        skills_used=["summarize_file"],
        skill_calls_count=1,
        skill_results=[{"skill_name": "summarize_file", "ok": True}],
    )

    rendered = render_agent_result(
        result=result,
        output_mode="trace",
        provider_line="provider: fake",
        mask_fn=lambda value: value,
    )

    assert "skills_used" in rendered
    assert "skill_calls_count" in rendered
    assert "skill_call_started" in rendered
    assert "skill_step_started" in rendered
    assert "skill_call_completed" in rendered
    assert "context_updated" in rendered
