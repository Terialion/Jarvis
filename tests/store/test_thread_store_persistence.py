from __future__ import annotations

from pathlib import Path

from src.jarvis.store.thread_store import ThreadStore
from tests.store._helpers import make_agent_result


def test_append_turn_persists_after_restart(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    store = ThreadStore(db_path=path)
    thread = store.create_thread(title="Persist turns")
    store.append_turn(thread.thread_id, make_agent_result(session_id=thread.thread_id, turn_id="turn_001"), user_input="hello")

    reopened = ThreadStore(db_path=path)
    turns = reopened.get_recent_turns(thread.thread_id)
    assert len(turns) == 1
    assert turns[0].turn_id == "turn_001"
    assert turns[0].input_redacted == "hello"
