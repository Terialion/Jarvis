from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.core.memory.store import PersistentMemoryStore


def test_secret_like_memory_value_is_flagged(tmp_path: Path):
    store = PersistentMemoryStore(str(tmp_path / "mem.json"))
    out = store.write({"memory_type": "failure_memory", "key": "token", "value": "sk-test-1234567890"})
    assert out["ok"] is True
    assert out["data"]["secret_rejected"] is True
