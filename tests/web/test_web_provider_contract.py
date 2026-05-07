from __future__ import annotations

from src.jarvis.web.providers.brave import BraveSearchProvider
from src.jarvis.web.providers.fake import FakeSearchProvider
from src.jarvis.web.schema import SearchQuery
from src.jarvis.web.search import run_web_search


def test_fake_provider_implements_contract():
    response = FakeSearchProvider().search(SearchQuery(query="Flink CDC CAST STRING bug", top_k=3))

    assert response.run.provider == "fake"
    assert response.run.ok is True
    assert response.run.result_count >= 1
    assert response.results[0].provider == "fake"


def test_brave_provider_returns_structured_error_until_configured():
    provider = BraveSearchProvider()
    response = provider.search(SearchQuery(query="Flink CDC CAST STRING bug", top_k=3))

    assert response.run.provider == "brave"
    assert response.run.ok is False
    assert "provider_not_configured" in str(response.run.error)
    assert response.results == []


def test_web_search_with_non_default_provider_returns_structured_failure_not_crash():
    result = run_web_search(SearchQuery(query="Flink CDC CAST STRING bug", provider="brave", top_k=3))

    assert result.ok is False
    assert result.runs[0]["provider"] == "brave"
