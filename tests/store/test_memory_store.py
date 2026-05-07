from __future__ import annotations

from pathlib import Path

from src.jarvis.store.memory_store import MemoryStore


def test_user_and_project_memory_are_separated(tmp_path: Path):
    store = MemoryStore(db_path=tmp_path / "jarvis.db")
    store.set_user_memory("name", "alice")
    store.set_project_memory("project-a", "phase", "17")
    store.set_project_memory("project-b", "phase", "other")

    assert store.get_user_memory()["name"] == "alice"
    assert store.get_project_memory("project-a")["phase"] == "17"
    assert store.get_project_memory("project-b")["phase"] == "other"


def test_memory_clear_and_delete(tmp_path: Path):
    store = MemoryStore(db_path=tmp_path / "jarvis.db")
    store.set_user_memory("name", "alice")
    store.delete_user_memory("name")
    assert store.get_user_memory() == {}
    store.set_project_memory("project-a", "phase", "17")
    store.clear_project_memory("project-a")
    assert store.get_project_memory("project-a") == {}
