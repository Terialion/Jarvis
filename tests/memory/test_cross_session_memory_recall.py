from pathlib import Path
import sys


from jarvis.core.memory.retriever import MemoryRetriever
from jarvis.core.memory.store import PersistentMemoryStore


def test_cross_session_recall(tmp_path: Path):
    store = PersistentMemoryStore(str(tmp_path / "mem.json"))
    store.write({"memory_type": "project_memory", "key": "test_command", "value": "pytest -q", "project_id": "p1", "session_id": "s1"})
    rows = MemoryRetriever(store).retrieve(project_id="p1", query="pytest")
    assert rows
