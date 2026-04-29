import json
from pathlib import Path


def test_operator_api_verification_artifact_fields():
    p = Path("d:/jarvis/temp/gap_closure/operator_api_verification.json")
    assert p.exists()
    payload = json.loads(p.read_text(encoding="utf-8"))
    required = [
        "route_summary",
        "skill_summary",
        "risk_summary",
        "recovery_summary",
        "rethink_summary",
        "hooks_summary",
        "memory_summary",
        "subagent_summary",
        "demo_summary",
        "approval_queue_available",
        "patch_review_available",
    ]
    for key in required:
        assert key in payload
