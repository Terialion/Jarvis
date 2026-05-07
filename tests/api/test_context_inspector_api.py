from __future__ import annotations

from pathlib import Path

from src.jarvis.api.server import JarvisApiState, route_request
from src.jarvis.agent.skill_context import ActiveTaskState, HandoffSummary, SkillObservation
from src.jarvis.store.memory_store import MemoryStore
from src.jarvis.store.thread_store import ThreadStore
from src.jarvis.web.research_context import ResearchObservation


def test_context_inspector_returns_redacted_background_only_payload(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "jarvis.db"
    thread_store = ThreadStore(db_path=db_path)
    memory_store = MemoryStore(db_path=db_path)
    thread = thread_store.create_thread(title="context", metadata={"project_id": "proj"})
    thread_store.append_message(thread.thread_id, "user", "hello")
    thread_store.append_skill_observation(
        thread.thread_id,
        SkillObservation(skill_name="repo_overview", summary="saw OPENAI_API_KEY=sk-secret", facts={}, related_files=["README.md"], tool_calls=[]),
        turn_id="turn_1",
    )
    thread_store.append_research_observation(
        thread.thread_id,
        ResearchObservation(
            query="q",
            search_tasks=[],
            sources=[{"url": "https://example.com", "token": "OPENAI_API_KEY=sk-secret"}],
            evidence=[{"quote": "OPENAI_API_KEY=sk-secret", "source": "https://example.com"}],
            answer_summary="summary",
            confidence=0.8,
            remaining_questions=[],
        ),
        turn_id="turn_1",
    )
    active = ActiveTaskState.new(user_goal="inspect", current_phase="active")
    thread_store.save_active_task(thread.thread_id, active)
    thread_store.save_handoff_summary(
        thread.thread_id,
        HandoffSummary(
            user_goal="inspect",
            current_state="saved",
            completed_work=[],
            remaining_work=[],
            context_to_keep=[],
            risks=[],
        ),
    )
    memory_store.set_user_memory("note", "OPENAI_API_KEY=sk-secret")
    memory_store.set_project_memory("proj", "mode", "background")
    monkeypatch.setattr("src.jarvis.api.server.ThreadStore", lambda: ThreadStore(db_path=db_path))
    monkeypatch.setattr("src.jarvis.api.server.MemoryStore", lambda db_path=db_path: MemoryStore(db_path=db_path))
    status, payload = route_request(JarvisApiState(), "GET", f"/api/context/{thread.thread_id}")
    assert status == 200
    data = payload["data"]
    assert data["background_only_notice"]
    assert "OPENAI_API_KEY=sk-secret" not in str(data)
