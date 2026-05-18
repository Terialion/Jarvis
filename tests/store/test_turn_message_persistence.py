from __future__ import annotations

from pathlib import Path

from src.jarvis.store import ThreadStore


def test_append_message_persists_after_restart(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    store = ThreadStore(sessions_dir=path)
    thread = store.create_thread(title="Persist messages")
    store.append_message(thread["thread_id"], "user", "remember this")

    reopened = ThreadStore(sessions_dir=path)
    messages = reopened.get_recent_messages(thread["thread_id"])
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "remember this"
