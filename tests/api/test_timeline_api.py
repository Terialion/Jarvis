from __future__ import annotations

from pathlib import Path

from src.jarvis.api.server import JarvisApiState, route_request
from src.jarvis.agent.types import AgentRunResult
from src.jarvis.api.timeline import timeline_from_agent_result
from src.jarvis.store.thread_store import ThreadStore
from src.jarvis.web.research_context import ResearchObservation


def test_timeline_builds_from_agent_events():
    result = AgentRunResult(
        ok=True,
        session_id="thread_timeline",
        turn_id="turn_timeline",
        final_answer="Done.",
        events=[
            {"event_id": "evt1", "turn_id": "turn_timeline", "type": "turn_started", "payload": {"text": "hello"}},
            {"event_id": "evt2", "turn_id": "turn_timeline", "type": "web_search_started", "payload": {"query": "jarvis"}},
            {"event_id": "evt3", "turn_id": "turn_timeline", "type": "tool_call_completed", "payload": {"tool_name": "web.fetch"}},
        ],
        summary={"human": "Done", "machine": {}},
        stop_reason="completed",
        tool_calls=[],
        tool_results=[],
        status="completed",
        output_type="answer",
        available_skills=[],
        loaded_skills=[],
        skill_loads_count=0,
        skills_used=[],
        skill_calls_count=0,
        skill_results=[],
        model_backend="fake",
        model_provider="fake",
        model_name="fake",
    )
    timeline = timeline_from_agent_result(result).to_dict()
    assert any(item["type"] == "user_message" for item in timeline["items"])
    assert any(item["type"] == "web_search" for item in timeline["items"])


def test_thread_timeline_api_builds_from_store(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "jarvis.db"
    store = ThreadStore(db_path=db_path)
    thread = store.create_thread(title="timeline")
    store.append_message(thread.thread_id, "user", "hello")
    store.append_tool_call(thread.thread_id, "turn_1", {"id": "call_1", "name": "web.fetch", "arguments": {"url": "https://example.com"}})
    store.append_research_observation(
        thread.thread_id,
        ResearchObservation(
            query="jarvis timeline",
            search_tasks=[],
            sources=[{"url": "https://example.com", "title": "Example"}],
            evidence=[{"quote": "evidence", "source": "https://example.com"}],
            answer_summary="summary",
            confidence=0.7,
            remaining_questions=[],
        ),
        turn_id="turn_1",
    )
    monkeypatch.setattr("src.jarvis.api.server.ThreadStore", lambda: ThreadStore(db_path=db_path))
    status, payload = route_request(JarvisApiState(), "GET", f"/api/threads/{thread.thread_id}/timeline")
    assert status == 200
    items = payload["data"]["items"]
    assert any(item["type"] == "tool_call" for item in items)
    assert any(item["type"] == "source" for item in items)
    assert any(item["type"] == "evidence" for item in items)
