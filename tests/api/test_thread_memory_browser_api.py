from __future__ import annotations

from pathlib import Path

from src.jarvis.api.server import JarvisApiState, route_request
from src.jarvis.agent.skill_context import SkillObservation
from src.jarvis.store.memory_store import MemoryStore
from src.jarvis.store import ThreadStore
from src.jarvis.web.research_context import ResearchObservation


def test_thread_and_memory_browser_routes(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "jarvis.db"
    thread_store = ThreadStore(sessions_dir=db_path)
    memory_store = MemoryStore(memory_md_dir=db_path)
    thread = thread_store.create_thread(title="browser", metadata={"project_id": "api"})
    thread_store.append_message(thread["thread_id"], "assistant", "stored")
    thread_store.append_skill_observation(
        thread["thread_id"],
        SkillObservation(skill_name="repo_overview", summary="summary", facts={}, related_files=[], tool_calls=[]),
        turn_id="turn_1",
    )
    thread_store.append_research_observation(
        thread["thread_id"],
        ResearchObservation(
            query="q",
            search_tasks=[],
            sources=[{"url": "https://example.com"}],
            evidence=[{"quote": "evidence"}],
            answer_summary="summary",
            confidence=0.6,
            remaining_questions=[],
        ),
        turn_id="turn_1",
    )
    memory_store.set_user_memory("owner", "alice")
    memory_store.set_project_memory("api", "mode", "control_surface")
    monkeypatch.setattr("src.jarvis.api.server.ThreadStore", lambda: ThreadStore(sessions_dir=db_path))
    monkeypatch.setattr("src.jarvis.api.server.MemoryStore", lambda: MemoryStore(memory_md_dir=db_path))

    status_threads, payload_threads = route_request(JarvisApiState(), "GET", "/api/threads")
    assert status_threads == 200
    assert any(row["thread_id"] == thread["thread_id"] for row in payload_threads["data"])

    status_open, payload_open = route_request(JarvisApiState(), "GET", f"/api/threads/{thread['thread_id']}/observations")
    assert status_open == 200
    assert payload_open["data"]["skills"]
    assert payload_open["data"]["research"]

    status_memory, payload_memory = route_request(JarvisApiState(), "GET", "/api/memory")
    assert status_memory == 200
    assert payload_memory["data"]["user"]["owner"] == "alice"
