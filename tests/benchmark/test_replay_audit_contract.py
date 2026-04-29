import json
from pathlib import Path


def test_replay_audit_contract():
    path = Path("d:/jarvis/temp/gap_closure/random_replay_audit.json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "audited_rounds" in payload

