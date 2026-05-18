from pathlib import Path

from jarvis.core.memory.retriever import MemoryRetriever
from jarvis.store.memory_store import MemoryStore


def test_rethink_lesson_can_be_written_and_retrieved(tmp_path: Path):
    store = MemoryStore(memory_md_dir=tmp_path / "mem")
    store.remember(memory_type="rethink_memory", key="failure_signature:x", value="use safer strategy")
    retriever = MemoryRetriever(store)
    rows = retriever.retrieve(project_id=None, query="failure_signature:x")
    assert len(rows) >= 1
