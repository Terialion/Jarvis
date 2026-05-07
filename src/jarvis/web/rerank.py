from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from .schema import SearchResult


def canonicalize_result_url(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", "", ""))


def dedup_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    deduped: list[SearchResult] = []
    for item in results:
        key = canonicalize_result_url(item.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def rerank_results(results: list[SearchResult], query: str) -> list[SearchResult]:
    query_terms = {part for part in str(query or "").lower().split() if part}

    def score(item: SearchResult) -> tuple[int, int]:
        weight = 0
        if item.source_type == "official_docs":
            weight += 30
        elif item.source_type in {"github_issue", "github_pr"}:
            weight += 20
        elif item.source_type == "release_notes":
            weight += 15
        elif item.source_type == "forum":
            weight -= 10
        haystack = f"{item.title} {item.snippet}".lower()
        overlap = sum(1 for term in query_terms if term in haystack)
        weight += overlap
        return (weight, -item.rank)

    deduped = dedup_results(results)
    reranked = sorted(deduped, key=score, reverse=True)
    for index, item in enumerate(reranked, start=1):
        item.rank = index
    return reranked

