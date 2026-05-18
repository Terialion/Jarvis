from __future__ import annotations

from pathlib import Path

from src.jarvis.store import ThreadStore


def test_tool_call_and_result_persist_after_restart(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    store = ThreadStore(sessions_dir=path)
    thread = store.create_thread(title="Persist tool calls")
    store.append_tool_call(thread["thread_id"], "turn_001", {"id": "call_001", "name": "web.fetch", "arguments": {"url": "https://example.com"}})
    store.append_tool_result(thread["thread_id"], "turn_001", {"call_id": "call_001", "name": "web.fetch", "ok": True, "content": "ok"})

    reopened = ThreadStore(sessions_dir=path)
    calls = reopened.get_tool_calls(thread["thread_id"])
    matching = [c for c in calls if c["call_id"] == "call_001"]
    assert len(matching) == 1
    assert matching[0]["tool_name"] == "web.fetch"
