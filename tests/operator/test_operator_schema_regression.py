import json
from pathlib import Path


SCHEMA_DIR = Path("d:/jarvis/docs/schemas/operator")
SCHEMA_FILES = [
    "operator_dashboard.schema.json",
    "operator_run_list.schema.json",
    "operator_run_detail.schema.json",
    "operator_run_trace.schema.json",
    "operator_skill_hits.schema.json",
    "operator_tool_calls.schema.json",
    "operator_stop_summary.schema.json",
]


def _assert_required_keys(schema_name: str, payload: dict) -> None:
    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    for key in schema["required"]:
        assert key in payload, f"{schema_name} missing required key: {key}"


def test_operator_schema_files_exist_and_valid_json() -> None:
    assert SCHEMA_DIR.exists()
    version_doc = (SCHEMA_DIR / "SCHEMA_VERSION.md").read_text(encoding="utf-8")
    assert "operator.operator_dashboard" in version_doc
    for filename in SCHEMA_FILES:
        raw = (SCHEMA_DIR / filename).read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert parsed["x-schema-version"] == "1.0.0"


def test_operator_schema_required_keys_match_sample_payloads() -> None:
    _assert_required_keys(
        "operator_dashboard.schema.json",
        {
            "run_count": 0,
            "last_updated": "",
            "gateway_summary": {},
            "active_runs_summary": {},
            "recent_runs": {},
            "channels_summary": {},
            "nodes_summary": {},
            "gate_summary": {},
            "review_summary": {},
            "runtime_observability_summary": {},
        },
    )
    _assert_required_keys("operator_run_list.schema.json", {"items": [], "count": 0, "total_runs": 0})
    _assert_required_keys(
        "operator_run_detail.schema.json",
        {"run_id": "x", "status": "completed", "steps": [], "run": {}, "current_state": "completed", "step_trace": {}, "skill_hits": {}, "tool_calls": {}, "stop": {}},
    )
    _assert_required_keys("operator_run_trace.schema.json", {"run_id": "x", "events": [], "total_duration_ms": 0, "task_id": "t", "items": [], "count": 0})
    _assert_required_keys(
        "operator_skill_hits.schema.json",
        {"skill_name": "test", "hit_count": 1, "last_hit": "2025-01-01", "run_id": "x", "task_id": "t", "items": [], "active_skills": [], "evaluation": {}},
    )
    _assert_required_keys("operator_tool_calls.schema.json", {"tool_name": "read_file", "call_count": 1, "avg_duration_ms": 10, "run_id": "x", "task_id": "t", "items": [], "count": 0})
    _assert_required_keys(
        "operator_stop_summary.schema.json",
        {
            "run_id": "x",
            "stop_reason": "repeated_failure_stop",
            "final_summary": "Test summary",
            "task_id": "t",
            "runtime_status": "stopped",
            "retry_count": 1,
            "fallback_type": "fallback_to_human_review",
            "approval_required": False,
            "approval_state": "not_required",
        },
    )
