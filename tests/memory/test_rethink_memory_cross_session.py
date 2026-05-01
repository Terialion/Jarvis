from pathlib import Path
import sys


from jarvis.core.memory.retriever import MemoryRetriever
from jarvis.core.memory.store import PersistentMemoryStore


def test_rethink_memory_cross_session_lookup(tmp_path: Path):
    store = PersistentMemoryStore(str(tmp_path / "mem.json"))
    store.write({"memory_type": "rethink_memory", "key": "sig:test_failed", "value": "retry with safer strategy", "project_id": "p1"})
    rows = MemoryRetriever(store).retrieve(project_id="p1", query="safer strategy")
    assert rows
