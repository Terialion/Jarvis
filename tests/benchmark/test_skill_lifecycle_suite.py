from __future__ import annotations

from benchmarks import run_benchmark


def test_skill_lifecycle_suite_runs_and_emits_metrics():
    result = run_benchmark.run_suite("skill_lifecycle", model_mode="fake")
    assert result["suite"] == "skill_lifecycle"
    assert result["total"] >= 1
    assert "skill_lifecycle_metrics" in result["metrics"]
    assert any(row["passed"] for row in result["results"])
