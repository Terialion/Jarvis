from __future__ import annotations

from src.jarvis.web.schema import SearchQuery
from src.jarvis.web.search import run_web_search


def test_web_search_run_contains_provider_error_flag():
    result = run_web_search(SearchQuery(query="provider error", provider="auto"))
    run = result.runs[0]
    assert result.ok is False
    assert run["provider_error"] is True
    assert run["no_results"] is False


def test_web_search_run_contains_no_results_flag():
    result = run_web_search(SearchQuery(query="no results", provider="auto"))
    run = result.runs[0]
    assert run["provider_error"] is False
    assert run["no_results"] is True
    assert run["result_count"] == 0


def test_web_search_deduplicates_duplicate_urls():
    result = run_web_search(SearchQuery(query="duplicate", provider="auto"))
    urls = [row["url"] for row in result.results]
    assert len(urls) == len(set(urls))

