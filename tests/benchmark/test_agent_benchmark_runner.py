from __future__ import annotations

from benchmarks.run_benchmark import run_suite


def test_benchmark_runner_smoke():
    payload = run_suite("jarvis_core", max_cases=2)
    assert payload["suite"] == "jarvis_core"
    assert payload["total"] <= 2
    assert "results" in payload

