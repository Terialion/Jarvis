from __future__ import annotations

from benchmarks import run_benchmark


def test_allowed_tools_enforcement_case_emits_denied_event():
    case = next(case for case in run_benchmark._load_cases("context_skill") if case.id == "context_skill_allow_001")
    run_result = run_benchmark._run_case(case, model_mode="fake")
    event_types = [event.get("type") for event in run_result["events"]]
    assert "skill_tool_denied" in event_types
    assert "tool_not_allowed_by_skill" in (run_result["summary"]["machine"].get("risks") or [])
