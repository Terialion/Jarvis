from __future__ import annotations

from benchmarks import run_benchmark


def test_skill_execution_case_uses_executable_skill():
    case = next(case for case in run_benchmark._load_cases("context_skill") if case.id == "context_skill_exec_001")
    run_result = run_benchmark._run_case(case, model_mode="fake")
    assert "summarize_file" in run_result["skills_used"]
    assert run_result["skill_calls_count"] >= 1
    assert any(call.get("name") == "repo_reader.read_file" for call in run_result["tool_calls"])
    event_types = {event.get("type") for event in run_result["events"]}
    assert "skill_call_started" in event_types
    assert "skill_call_completed" in event_types
