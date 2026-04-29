import json
from pathlib import Path


def test_operator_api_verification_contract_file():
    path = Path("d:/jarvis/temp/gap_closure/operator_api_verification.json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = [
        "ok",
        "route_summary",
        "skill_summary",
        "risk_summary",
        "recovery_summary",
        "rethink_summary",
        "hooks_summary",
        "memory_summary",
        "subagent_summary",
        "demo_summary",
    ]
    for key in required:
        assert key in payload

