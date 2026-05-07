from __future__ import annotations

from benchmarks.run_benchmark import run_suite


def test_control_surface_metrics_present():
    result = run_suite("control_surface", model_mode="fake")
    metrics = dict(result.get("metrics") or {}).get("control_surface_metrics") or {}
    assert metrics["control_surface_api_success_rate"] == 1.0
    assert metrics["timeline_build_success_rate"] == 1.0
    assert metrics["ui_redaction_success_rate"] == 1.0
    assert metrics["control_surface_secret_leak_count"] == 0
    assert metrics["browser_boundary_preserved_count"] > 0
    assert metrics["second_agent_loop_violation_count"] == 0
