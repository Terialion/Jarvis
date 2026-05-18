from __future__ import annotations

from benchmarks import run_benchmark


def test_web_research_suite_contains_skill_guided_case():
    cases = run_benchmark._load_cases("web_research")
    case_ids = {case.id for case in cases}
    assert "web_research_skill_guided_web_search_001" in case_ids

