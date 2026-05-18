from __future__ import annotations

from pathlib import Path

from src.jarvis.store import ThreadStore


def test_schema_version_survives_reopen(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    ThreadStore(sessions_dir=path)
    reopened = ThreadStore(sessions_dir=path)
    assert reopened.schema_version() in (2, 3)
