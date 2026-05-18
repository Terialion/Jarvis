from pathlib import Path

from jarvis.core.memory.retriever import MemoryRetriever
from jarvis.store.memory_store import MemoryStore


def test_cross_session_recall(tmp_path: Path):
    store = MemoryStore(memory_md_dir=tmp_path / "mem")
    store.remember(memory_type="project_memory", key="test_command", value="pytest -q", project_id="p1")
    rows = MemoryRetriever(store).retrieve(project_id="p1", query="pytest")
    assert rows
