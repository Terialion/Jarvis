from __future__ import annotations

from benchmarks import run_benchmark


def test_context_skill_suite_loads_all_case_categories():
    cases = run_benchmark._load_cases("context_skill")
    categories = {case.category for case in cases}
    assert "skill_loading" in categories
    assert "skill_execution" in categories
    assert "allowed_tools_enforcement" in categories
    assert "multi_turn_context" in categories
    assert "context_compaction" in categories
    assert "skill_safety" in categories


def test_context_skill_runner_smoke_fake_mode():
    payload = run_benchmark.run_suite("context_skill", max_cases=2, model_mode="fake")
    assert payload["suite"] == "context_skill"
    assert payload["total"] == 2
    assert "metrics" in payload
