from __future__ import annotations

from dataclasses import dataclass

from ..schema import SearchQuery, SearchResult, SearchRun


@dataclass
class ProviderSearchResponse:
    run: SearchRun
    results: list[SearchResult]


class BaseSearchProvider:
    provider_name = "base"
    engine_name = "base"

    def search(self, query: SearchQuery) -> ProviderSearchResponse:
        raise NotImplementedError

