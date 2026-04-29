import json
from pathlib import Path


def test_random_replay_audit_artifact_exists():
    p = Path("d:/jarvis/temp/gap_closure/random_replay_audit.json")
    assert p.exists()
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert "audited_rounds" in payload
