from jarvis.store.memory_store import MemoryStore
from jarvis.core.memory.retriever import MemoryRetriever


def test_project_test_command_recall_e2e(tmp_path):
    store = MemoryStore(memory_md_dir=tmp_path / "mem")
    store.remember(memory_type="project", key="test_command", value="pytest -q")
    recalled = MemoryRetriever(store).recall(memory_type="project", key="test_command", limit=1)
    assert recalled[-1]["value"] == "pytest -q"
