from __future__ import annotations

from src.jarvis.web.schema import FetchRequest, ReadableDocument, SearchQuery, SearchResult


def test_web_schema_to_dict_shapes_are_stable():
    query = SearchQuery(query="query", provider="auto", top_k=5, site="github.com")
    result = SearchResult(title="t", url="https://example.com", snippet="s", rank=1, source_type="documentation")
    request = FetchRequest(url="https://example.com")
    document = ReadableDocument(
        url="https://example.com",
        final_url="https://example.com",
        title="Example",
        text="hello",
        source_type="documentation",
    )

    assert query.to_dict()["query"] == "query"
    assert result.to_dict()["source_type"] == "documentation"
    assert request.to_dict()["extract_mode"] == "markdown"
    assert document.to_dict()["is_untrusted"] is True
