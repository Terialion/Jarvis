from jarvis.store.memory_store import MemoryStore
from jarvis.core.memory.retriever import MemoryRetriever


def test_memory_retrieval_for_project_context(tmp_path):
    store = MemoryStore(memory_md_dir=tmp_path / "mem")
    store.remember(memory_type="project", key="test_command", value="pytest -q")
    r = MemoryRetriever(store)
    items = r.recall(memory_type="project", key="test_command", limit=1)
    assert items and items[-1]["value"] == "pytest -q"
