from __future__ import annotations

from src.jarvis.web.cache import WebCache, make_fetch_cache_key, make_search_cache_key, normalize_url
from src.jarvis.web.source_classifier import classify_source


def test_cache_keys_and_url_normalization_are_stable():
    assert normalize_url("HTTPS://Example.com/docs/page?utm_source=x&foo=1#frag") == "https://example.com/docs/page?foo=1"
    assert make_fetch_cache_key("https://Example.com/docs/page?utm_source=x&foo=1#frag") == "https://example.com/docs/page?foo=1"
    assert make_search_cache_key("fake", "fake", "query", 5, "month", "github.com") == "fake|fake|query|5|month|github.com"

    cache = WebCache(ttl_s=60)
    cache.set_search("k", {"ok": True})
    assert cache.get_search("k") == {"ok": True}


def test_source_classifier_identifies_expected_source_types():
    assert classify_source("https://github.com/apache/flink-cdc/issues/123") == "github_issue"
    assert classify_source("https://github.com/apache/flink-cdc/pull/456") == "github_pr"
    assert classify_source("https://nightlies.apache.org/flink/flink-cdc-docs-master/docs/") == "official_docs"
    assert classify_source("https://project.example/release-notes/changelog") == "release_notes"
    assert classify_source("https://forum.example/thread") == "forum"
