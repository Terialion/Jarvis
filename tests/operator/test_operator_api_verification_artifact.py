import json
from pathlib import Path


def test_operator_api_verification_artifact_exists():
    p = Path("d:/jarvis/temp/gap_closure/operator_api_verification.json")
    assert p.exists()
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload.get("ok") is True
