from __future__ import annotations

from pathlib import Path

from src.jarvis.cli import ShellState, _shell_context, _shell_memory, _shell_threads
from src.jarvis.store.memory_store import MemoryStore
from src.jarvis.store.thread_store import ThreadStore


def test_context_threads_and_memory_commands(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "jarvis.db"
    monkeypatch.setattr("src.jarvis.cli._thread_store", lambda: ThreadStore(db_path=db_path))
    monkeypatch.setattr("src.jarvis.cli._memory_store", lambda: MemoryStore(db_path=db_path))
    state = ShellState("http://127.0.0.1:8765")
    state.current_project_id = "p17"

    saved = _shell_context(state, ["save"])
    assert "Context saved:" in saved
    listed = _shell_threads(state, ["list"])
    assert "Threads:" in listed
    opened = _shell_threads(state, ["open", state.current_thread_id])
    assert f"Thread: {state.current_thread_id}" in opened
    resumed = _shell_context(state, ["resume", state.current_thread_id])
    assert "background-only" in resumed

    edited = _shell_memory(state, ["edit", "owner", "alice"])
    assert "Memory updated: owner" in edited
    shown = _shell_memory(state, ["show"])
    assert "owner: alice" in shown
    cleared = _shell_memory(state, ["clear"])
    assert "User memory cleared." in cleared
