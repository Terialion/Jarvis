from __future__ import annotations

from pathlib import Path

from src.jarvis.store.thread_store import ThreadStore


def test_tool_call_and_result_persist_after_restart(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    store = ThreadStore(db_path=path)
    thread = store.create_thread(title="Persist tool calls")
    store.append_tool_call(thread.thread_id, "turn_001", {"id": "call_001", "name": "web.fetch", "arguments": {"url": "https://example.com"}})
    store.append_tool_result(thread.thread_id, "turn_001", {"call_id": "call_001", "name": "web.fetch", "ok": True, "content": "ok"})

    reopened = ThreadStore(db_path=path)
    with reopened._connect() as conn:
        row = conn.execute("SELECT tool_name, status FROM tool_calls WHERE call_id='call_001'").fetchone()
    assert row is not None
    assert str(row["tool_name"]) == "web.fetch"
    assert str(row["status"]) == "completed"
