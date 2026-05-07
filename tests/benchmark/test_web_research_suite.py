from __future__ import annotations

from functools import lru_cache

from benchmarks import run_benchmark


@lru_cache(maxsize=1)
def _web_research_payload():
    return run_benchmark.run_suite("web_research", model_mode="fake")


def test_web_research_suite_has_phase14_categories():
    cases = run_benchmark._load_cases("web_research")
    categories = {case.category for case in cases}

    assert "provider_selection" in categories
    assert "search_then_fetch" in categories
    assert "fetch_safety" in categories
    assert "official_source_bias" in categories
    assert "github_issue_lookup" in categories
    assert "evidence_extraction" in categories
    assert "stale_source_detection" in categories
    assert "context_reuse" in categories
    assert "prompt_injection_safety" in categories


def test_web_research_suite_runs_offline_fake_green():
    payload = _web_research_payload()

    assert payload["suite"] == "web_research"
    assert payload["total"] >= 9
    assert payload["pass_rate"] == 1.0
    assert "web_research_metrics" in payload["metrics"]


def test_web_fetch_safety_benchmark_blocks_redirect_fixture():
    payload = _web_research_payload()
    row = next(item for item in payload["results"] if item["case_id"] == "web_research_fetch_safety_001")
    machine = row["run_result"]["summary"]["machine"]

    assert row["passed"] is True
    assert machine["web_fetch_blocked_count"] >= 1
    assert "web_fetch_blocked" in {event["type"] for event in row["run_result"]["events"]}


def test_web_research_context_reuse_case_reuses_research_observation():
    payload = _web_research_payload()
    row = next(item for item in payload["results"] if item["case_id"] == "web_research_context_reuse_001")
    machine = row["run_result"]["summary"]["machine"]

    assert row["passed"] is True
    assert machine["context_reuse"] is True
    assert machine["research_context_reused"] is True
