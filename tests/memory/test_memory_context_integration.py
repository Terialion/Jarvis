import os
import sys


from jarvis.core.memory.store import PersistentMemoryStore
from jarvis.core.memory.retriever import MemoryRetriever


def test_memory_retrieval_for_project_context(tmp_path):
    store = PersistentMemoryStore(str(tmp_path / "mem.jsonl"))
    store.write({"memory_type": "project", "key": "test_command", "value": "pytest -q"})
    r = MemoryRetriever(store)
    items = r.recall(memory_type="project", key="test_command", limit=1)
    assert items and items[-1]["value"] == "pytest -q"
