from __future__ import annotations

from pathlib import Path

from src.jarvis.store.thread_store import ThreadStore
from tests.store._helpers import make_skill_observation


def test_skill_observation_persists_after_restart(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    store = ThreadStore(db_path=path)
    thread = store.create_thread(title="Persist skills")
    store.append_skill_observation(thread.thread_id, make_skill_observation(), turn_id="turn_001")

    reopened = ThreadStore(db_path=path)
    rows = reopened.get_skill_observations(thread.thread_id)
    assert len(rows) == 1
    assert rows[0].skill_name == "repo_overview"
