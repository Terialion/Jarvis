from pathlib import Path
import sys


from jarvis.core.memory.retriever import MemoryRetriever
from jarvis.core.memory.store import PersistentMemoryStore


def test_rethink_lesson_can_be_written_and_retrieved(tmp_path: Path):
    store = PersistentMemoryStore(str(tmp_path / "mem.json"))
    store.write({"memory_type": "rethink_memory", "key": "failure_signature:x", "value": "use safer strategy"})
    retriever = MemoryRetriever(store)
    rows = retriever.retrieve(project_id=None, query="failure_signature:x")
    assert len(rows) >= 1
