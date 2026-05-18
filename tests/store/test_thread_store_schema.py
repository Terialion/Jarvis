from __future__ import annotations

from pathlib import Path

from src.jarvis.store import ThreadStore


def test_thread_store_initializes_schema_and_version(tmp_path: Path):
    store = ThreadStore(sessions_dir=tmp_path / "jarvis.db")
    assert store.schema_version() in (2, 3)
    assert (tmp_path / "jarvis.db").exists()


def test_thread_store_create_get_list_thread(tmp_path: Path):
    store = ThreadStore(sessions_dir=tmp_path / "jarvis.db")
    thread = store.create_thread(title="Phase 17", metadata={"source": "test"})
    assert store.get_thread(thread["thread_id"]) is not None
    assert any(row["thread_id"] == thread["thread_id"] for row in store.list_threads())
