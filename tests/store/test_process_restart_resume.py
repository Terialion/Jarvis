from __future__ import annotations

from pathlib import Path

from src.jarvis.store.thread_store import ThreadStore
from tests.store._helpers import make_research_observation, make_skill_observation


def test_process_restart_can_resume_observations(tmp_path: Path):
    path = tmp_path / "jarvis.db"
    store = ThreadStore(db_path=path)
    thread = store.create_thread(title="Restart resume")
    store.append_skill_observation(thread.thread_id, make_skill_observation(), turn_id="turn_001")
    store.append_research_observation(thread.thread_id, make_research_observation(), turn_id="turn_001")

    reopened = ThreadStore(db_path=path)
    assert reopened.get_skill_observations(thread.thread_id)
    assert reopened.get_research_observations(thread.thread_id)
