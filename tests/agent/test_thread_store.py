from __future__ import annotations

from pathlib import Path

from src.jarvis.agent.store import ThreadStore
from src.jarvis.agent.types import ChatInput


def test_thread_store_jsonl_persistence(tmp_path: Path):
    store = ThreadStore(tmp_path / "agent_threads")
    chat = ChatInput(text="inspect repo", project_id="p1", cwd=str(tmp_path))
    session = store.create_or_resume_session(chat)
    session_id = session["session_id"]
    turn = store.create_turn(session_id)

    store.append_message(session_id, turn.turn_id, "user", "inspect repo")
    store.append_tool_call(session_id, turn.turn_id, {"id": "c1", "name": "repo_reader.search_files", "arguments": {}})
    store.append_tool_result(session_id, turn.turn_id, {"call_id": "c1", "name": "repo_reader.search_files", "ok": True})
    store.save_final_answer(session_id, turn.turn_id, "done")
    store.save_summary(session_id, turn.turn_id, {"machine": {"outcome": "completed"}})

    assert store.load_messages(session_id)
    assert store.load_turns(session_id)
    assert store.load_summaries(session_id)
    assert store.load_last_session_id() == session_id

