import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from jarvis.core.memory.store import PersistentMemoryStore

def test_memory_write_and_secret_redaction(tmp_path):
    s = PersistentMemoryStore(str(tmp_path / "m.json"))
    ok = s.write({"memory_type":"project","key":"test_cmd","value":"pytest -q"})
    secret = s.write({"memory_type":"project","key":"token","value":"api_key=abc"})
    assert ok["data"]["secret_rejected"] is False
    assert secret["data"]["secret_rejected"] is True
