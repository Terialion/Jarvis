from __future__ import annotations

import json

from src.jarvis.agent.types import AgentEvent, AgentRunResult, ChatInput, ToolCall, ToolResult


def test_types_to_dict_and_secret_redaction():
    chat = ChatInput(
        text="hello",
        metadata={"api_key": "secret-value", "nested": {"token": "abc", "safe": "ok"}},
    )
    payload = chat.to_dict()
    assert payload["metadata"]["api_key"] == "***"
    assert payload["metadata"]["nested"]["token"] == "***"
    assert payload["metadata"]["nested"]["safe"] == "ok"


def test_agent_run_result_serializable():
    event = AgentEvent.new(turn_id="turn_1", event_type="turn_started", payload={"x": 1})
    result = AgentRunResult(
        ok=True,
        session_id="s1",
        turn_id="t1",
        final_answer="done",
        events=[event.to_dict()],
        summary={"machine": {"outcome": "completed"}},
        stop_reason="completed",
        tool_calls=[ToolCall.new(name="repo_reader.search_files").to_dict()],
        tool_results=[ToolResult(call_id="c1", name="repo_reader.search_files", ok=True).to_dict()],
    )
    json.dumps(result.to_dict(), ensure_ascii=False)


def test_agent_run_result_redacts_secret_like_text():
    result = AgentRunResult(
        ok=True,
        session_id="s1",
        turn_id="t1",
        final_answer="OPENAI_API_KEY=sk-secret Authorization: Bearer abc token=xyz",
        events=[],
        summary={"machine": {"outcome": "completed"}},
        stop_reason="completed",
    )
    payload = result.to_dict()
    answer = payload["final_answer"]
    assert "sk-secret" not in answer
    assert "Authorization: Bearer abc" not in answer
    assert "token=xyz" not in answer
    assert "sk-" not in answer
    assert "Authorization: Bearer" not in answer
    assert "OPENAI_API_KEY=" not in answer
    assert "token=" not in answer
    assert "OPENAI_API_KEY:[REDACTED]" in answer


def test_agent_run_result_includes_skill_fields():
    result = AgentRunResult(
        ok=True,
        session_id="s1",
        turn_id="t1",
        final_answer="done",
        events=[],
        summary={"machine": {"outcome": "completed"}},
        stop_reason="completed",
        available_skills=["repo_overview", "summarize_file"],
        loaded_skills=["summarize_file"],
        skill_loads_count=1,
    )
    payload = result.to_dict()
    assert payload["available_skills"] == ["repo_overview", "summarize_file"]
    assert payload["loaded_skills"] == ["summarize_file"]
    assert payload["skill_loads_count"] == 1

