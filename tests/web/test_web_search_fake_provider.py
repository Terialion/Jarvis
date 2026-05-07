from __future__ import annotations

from src.jarvis.web.schema import SearchQuery
from src.jarvis.web.search import run_web_search


def test_web_search_fake_provider_success():
    result = run_web_search(SearchQuery(query="Flink CDC CAST STRING bug", provider="auto", top_k=5))

    assert result.ok is True
    assert len(result.results) >= 3
    assert result.documents == []
    assert result.runs[0]["provider"] == "fake"


def test_web_search_provider_error_is_structured():
    result = run_web_search(SearchQuery(query="provider error", provider="auto", top_k=5))

    assert result.ok is False
    assert result.results == []
    assert result.runs[0]["ok"] is False
    assert "fake_provider_error" in str(result.error)


def test_web_search_no_results_is_structured():
    result = run_web_search(SearchQuery(query="no results", provider="auto", top_k=5))

    assert result.ok is True
    assert result.results == []
    assert result.runs[0]["result_count"] == 0
