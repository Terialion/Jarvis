from pathlib import Path

from jarvis.core.memory.retriever import MemoryRetriever
from jarvis.store.memory_store import MemoryStore


def test_rethink_memory_cross_session_lookup(tmp_path: Path):
    store = MemoryStore(memory_md_dir=tmp_path / "mem")
    store.remember(memory_type="rethink_memory", key="sig:test_failed", value="retry with safer strategy", project_id="p1")
    rows = MemoryRetriever(store).retrieve(project_id="p1", query="safer strategy")
    assert rows
