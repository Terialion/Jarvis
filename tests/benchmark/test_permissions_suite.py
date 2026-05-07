from __future__ import annotations

from benchmarks import run_benchmark


def test_permissions_suite_runs_and_emits_metrics():
    result = run_benchmark.run_suite("permissions", model_mode="fake")
    assert result["suite"] == "permissions"
    assert result["total"] >= 1
    assert "permissions_metrics" in result["metrics"]
    assert any(row["passed"] for row in result["results"])
