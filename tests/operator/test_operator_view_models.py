import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core import (
    build_operator_dashboard_view,
    build_run_detail_view,
    build_run_list_view,
    build_run_skill_hits_view,
    build_run_step_trace_view,
    build_run_stop_summary_view,
    build_run_tool_calls_view,
)


def _sample_run() -> dict:
    return {
        "run_id": "react_run_1",
        "task_id": "task_1",
        "state": "completed",
        "traces": [
            {
                "step_number": 0,
                "observation": {"payload": {"step_number": 0, "pending_plan_steps": 3, "task_status": "running"}},
                "chosen_skill": "code_fix",
                "chosen_tool": "repo_reader.search_symbol",
                "action_input": {"tool": "repo_reader.search_symbol", "symbol": "return 1"},
                "action_result": {"ok": True, "data": {"matches": [{"path": "a.py"}]}, "meta": {"duration_ms": 5}},
                "check_result": {"passed": True, "outcome": "success"},
                "stop_reason": None,
            },
            {
                "step_number": 1,
                "observation": {"payload": {"step_number": 1, "pending_plan_steps": 2, "task_status": "running"}},
                "chosen_skill": "code_fix",
                "chosen_tool": "test_runner.run_test",
                "action_input": {"tool": "test_runner.run_test", "command": "pytest -q"},
                "action_result": {"ok": True, "data": {"passed": True}, "meta": {"duration_ms": 12}},
                "check_result": {"passed": True, "should_stop": True, "stop_reason": "success", "outcome": "test_passed"},
                "stop_reason": "success",
            },
        ],
        "stop_record": {"reason": "success", "detail": {"step": 1}},
        "retries": 0,
        "fallback": {"mode": "none", "detail": None},
        "skill_eval": {"run_id": "react_run_1", "total_steps": 2, "success_rate": 1.0},
        "route_result": {
            "domain": "inform",
            "intent": "retrieval.read",
            "confidence": 0.82,
            "attached_default_skills": ["skill.command_verify"],
            "planner_hints": {"task_shape": "single_step"},
            "approval_risk_hints": {"approval_required": False, "risk_level": "low"},
        },
        "route_quality_summary": {"route_quality": "high"},
        "recovery_effectiveness_summary": {"retry_count": 0, "recovery_records": 1},
        "approval_policy_summary": {"approval_events": 0, "approval_required_events": 0},
        "duration_ms": 42,
    }


def test_operator_run_views_build_correctly() -> None:
    run = _sample_run()
    run_list = build_run_list_view([run], limit=20)
    detail = build_run_detail_view(run)
    trace = build_run_step_trace_view(run)
    skills = build_run_skill_hits_view(run)
    tools = build_run_tool_calls_view(run)
    stop = build_run_stop_summary_view(run)

    assert run_list["count"] == 1
    assert run_list["items"][0]["run_id"] == "react_run_1"
    assert detail["run"]["runtime_status"] == "completed"
    assert detail["route_summary"]["domain"] == "inform"
    assert detail["route_quality_summary"]["route_quality"] == "high"
    assert trace["count"] == 2
    assert "strategy" in trace["items"][0]
    assert skills["active_skills"] == ["code_fix"]
    assert tools["count"] == 2
    assert stop["stop_reason"] == "success"


def test_operator_dashboard_view_with_sparse_data_stable() -> None:
    dashboard = build_operator_dashboard_view(
        gateway_summary={},
        active_runs_summary={"total_runs": 0, "active_runs": 0, "failed_or_stopped_runs": 0},
        recent_runs={"items": [], "count": 0, "total_runs": 0},
        channels_summary={},
        nodes_summary={},
        gate_summary={"available": False},
        review_summary={"total_tasks": 0},
        runtime_observability_summary={"gateway_status": "ok"},
    )
    assert "gateway_summary" in dashboard
    assert "recent_runs" in dashboard
    assert dashboard["active_runs_summary"]["total_runs"] == 0
