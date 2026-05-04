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

