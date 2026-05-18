from __future__ import annotations

from pathlib import Path

from src.jarvis.api.server import JarvisApiState, route_request
from src.jarvis.store.memory_store import MemoryStore
from src.jarvis.store import ThreadStore


def test_thread_and_memory_api_routes(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "jarvis.db"
    monkeypatch.setattr("src.jarvis.api.server.ThreadStore", lambda: ThreadStore(sessions_dir=db_path))
    monkeypatch.setattr("src.jarvis.api.server.MemoryStore", lambda: MemoryStore(memory_md_dir=db_path))
    state = JarvisApiState()

    status, payload = route_request(state, "POST", "/api/context/save", {"title": "saved"})
    assert status == 200
    thread_id = str(payload["data"]["thread_id"])

    status, payload = route_request(state, "GET", "/api/threads")
    assert status == 200
    assert any(row["thread_id"] == thread_id for row in payload["data"])

    status, payload = route_request(state, "GET", f"/api/threads/{thread_id}")
    assert status == 200
    assert payload["data"]["thread_id"] == thread_id

    status, payload = route_request(state, "POST", "/api/memory", {"key": "owner", "value": "alice"})
    assert status == 200
    assert payload["data"]["key"] == "owner"
