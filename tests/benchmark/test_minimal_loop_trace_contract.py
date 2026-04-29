import json
from pathlib import Path


def test_minimal_loop_trace_contract_fields():
    path = Path("d:/jarvis/temp/gap_closure/minimal_loop_trace.json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = [
        "user_input",
        "guard_context",
        "intent_policy",
        "planner_heavy_react",
        "skill_seed_match",
        "tool_call",
        "approval_risk",
        "rethink",
        "recovery",
        "replay_event",
        "operator_summary",
        "memory_write",
        "final_response",
    ]
    for key in required:
        assert key in payload

