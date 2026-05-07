from __future__ import annotations

from benchmarks.run_benchmark import run_suite


def test_persistent_memory_metrics_present():
    result = run_suite("persistent_memory", model_mode="fake")
    metrics = dict(result.get("metrics") or {}).get("persistent_memory_metrics") or {}
    assert metrics["metric_semantics"] == "relevant_case_denominator"
    assert "thread_persist_success_rate" in metrics
    assert "persistent_secret_leak_count" in metrics
    assert metrics["thread_persist_success_rate"] == 1.0
    assert metrics["context_resume_success_rate"] == 1.0
    assert metrics["process_restart_resume_success_rate"] == 1.0
    assert metrics["skill_observation_persist_rate"] == 1.0
    assert metrics["research_observation_persist_rate"] == 1.0
    assert metrics["thread_persist_relevant_case_count"] >= 1
    assert metrics["persistent_secret_leak_count"] == 0
