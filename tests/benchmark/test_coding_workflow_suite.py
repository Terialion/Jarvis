from __future__ import annotations

from benchmarks.run_benchmark import run_suite


def test_coding_suite_runs_fake():
    result = run_suite("coding", model_mode="fake")
    assert result["suite"] == "coding"
    assert result["pass_rate"] == 1.0


def test_coding-workflow_suite_runs_fake():
    result = run_suite("coding-workflow", model_mode="fake")
    assert result["suite"] == "coding-workflow"
    assert result["pass_rate"] == 1.0
