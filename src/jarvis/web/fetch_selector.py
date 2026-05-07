from __future__ import annotations

from .schema import SearchResult


class FetchSelector:
    def __init__(self, *, max_fetch_urls: int = 5) -> None:
        self.max_fetch_urls = max_fetch_urls

    def select(self, results: list[SearchResult], intent_type: str) -> list[SearchResult]:
        selected: list[SearchResult] = []
        seen_urls: set[str] = set()
        seen_types: set[str] = set()
        for item in results:
            if item.url in seen_urls:
                continue
            if intent_type == "bug_verification" and item.source_type in {"official_docs", "github_issue", "github_pr"}:
                selected.append(item)
                seen_urls.add(item.url)
                seen_types.add(item.source_type)
            elif intent_type == "docs_lookup" and item.source_type in {"official_docs", "release_notes", "documentation"}:
                selected.append(item)
                seen_urls.add(item.url)
                seen_types.add(item.source_type)
            elif item.source_type not in seen_types:
                selected.append(item)
                seen_urls.add(item.url)
                seen_types.add(item.source_type)
            if len(selected) >= self.max_fetch_urls:
                break
        if intent_type == "bug_verification":
            has_official = any(item.source_type == "official_docs" for item in selected)
            has_github = any(item.source_type in {"github_issue", "github_pr"} for item in selected)
            if not has_official or not has_github:
                for item in results:
                    if item.url in seen_urls:
                        continue
                    if not has_official and item.source_type == "official_docs":
                        selected.append(item)
                        seen_urls.add(item.url)
                        has_official = True
                    elif not has_github and item.source_type in {"github_issue", "github_pr"}:
                        selected.append(item)
                        seen_urls.add(item.url)
                        has_github = True
                    if len(selected) >= self.max_fetch_urls or (has_official and has_github):
                        break
        return selected[: self.max_fetch_urls]

