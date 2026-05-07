from __future__ import annotations

from benchmarks.run_benchmark import run_suite


def test_persistent_memory_suite_runs_fake():
    result = run_suite("persistent_memory", model_mode="fake")
    assert result["suite"] == "persistent_memory"
    assert result["total"] >= 1
    assert result["pass_rate"] == 1.0
