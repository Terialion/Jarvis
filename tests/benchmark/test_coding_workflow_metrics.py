from __future__ import annotations

from benchmarks.run_benchmark import run_suite


def test_coding-workflow_metrics_present():
    result = run_suite("coding-workflow", model_mode="fake")
    metrics = dict(result.get("metrics") or {}).get("coding-workflow_metrics") or {}

    assert metrics["coding_review_success_rate"] == 1.0
    assert metrics["coding_fix_success_rate"] == 1.0
    assert metrics["patch_plan_success_rate"] == 1.0
    assert metrics["diff_preview_success_rate"] == 1.0
    assert metrics["coding_secret_leak_count"] == 0
