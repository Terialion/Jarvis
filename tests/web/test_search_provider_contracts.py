from __future__ import annotations

from src.jarvis.web.contracts import SearchRequest, SearchResult, SearchRun


def test_search_contracts_are_serializable():
    req = SearchRequest(
        query="today tech news",
        provider="fake",
        guided_by_skill="multi-search-engine",
        invocation_path="reference_skill_guided_tool_call",
        source="skill_guided",
    )
    result = SearchResult(
        title="Title",
        url="https://example.com",
        snippet="Snippet",
        rank=1,
        provider="fake",
        query=req.query,
    )
    run = SearchRun(request=req, ok=True, results=[result], result_count=1)
    payload = run.to_dict()
    assert payload["request"]["guided_by_skill"] == "multi-search-engine"
    assert payload["request"]["invocation_path"] == "reference_skill_guided_tool_call"
    assert payload["result_count"] == 1

