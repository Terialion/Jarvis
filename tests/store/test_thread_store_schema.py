from __future__ import annotations

from pathlib import Path

import pytest

from src.jarvis.store.thread_store import ThreadStore, ThreadStoreError


def test_thread_store_initializes_schema_and_version(tmp_path: Path):
    store = ThreadStore(db_path=tmp_path / "jarvis.db")
    assert store.schema_version() == 1
    assert (tmp_path / "jarvis.db").exists()


def test_thread_store_create_get_list_thread(tmp_path: Path):
    store = ThreadStore(db_path=tmp_path / "jarvis.db")
    thread = store.create_thread(title="Phase 17", metadata={"source": "test"})
    assert store.get_thread(thread.thread_id) is not None
    assert any(row.thread_id == thread.thread_id for row in store.list_threads())


def test_thread_store_bad_database_raises_structured_error(tmp_path: Path):
    path = tmp_path / "bad.db"
    path.write_text("not a sqlite database", encoding="utf-8")
    with pytest.raises(ThreadStoreError):
        ThreadStore(db_path=path)
