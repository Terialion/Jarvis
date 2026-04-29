from pathlib import Path

from jarvis.core.memory.store import PersistentMemoryStore


def test_project_memory_reuse(tmp_path: Path):
    store = PersistentMemoryStore(str(tmp_path / "mem.json"))
    store.write({"memory_type": "project_memory", "key": "cmd", "value": "pytest tests/core_v0 -q", "project_id": "repoA"})
    rows = store.read(memory_type="project_memory", key="cmd")
    assert len(rows) == 1
    assert "pytest" in rows[0]["value"]

