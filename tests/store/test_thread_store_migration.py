from __future__ import annotations

from pathlib import Path

from src.jarvis.store.thread_store import ThreadStore


def test_schema_version_survives_reopen(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    ThreadStore(db_path=path)
    reopened = ThreadStore(db_path=path)
    assert reopened.schema_version() == 1
