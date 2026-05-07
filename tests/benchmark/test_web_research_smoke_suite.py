from __future__ import annotations

from benchmarks import run_benchmark


def test_web_research_smoke_suite_loads_cases():
    cases = run_benchmark._load_cases("web_research_smoke")
    categories = {case.category for case in cases}

    assert "web_search_smoke" in categories
    assert "web_fetch_safety_smoke" in categories
    assert "web_research_reuse_smoke" in categories


def test_web_research_smoke_suite_runs_in_fake_mode():
    payload = run_benchmark.run_suite("web_research_smoke", model_mode="fake")

    assert payload["suite"] == "web_research_smoke"
    assert payload["total"] >= 3
    assert "web_research_smoke_metrics" in payload["metrics"]
