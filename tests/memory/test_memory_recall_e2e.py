import os
import sys


from jarvis.core.memory.store import PersistentMemoryStore
from jarvis.core.memory.retriever import MemoryRetriever


def test_project_test_command_recall_e2e(tmp_path):
    store = PersistentMemoryStore(str(tmp_path / "mem.jsonl"))
    store.write({"memory_type": "project", "key": "test_command", "value": "pytest -q"})
    recalled = MemoryRetriever(store).recall(memory_type="project", key="test_command", limit=1)
    assert recalled[-1]["value"] == "pytest -q"
