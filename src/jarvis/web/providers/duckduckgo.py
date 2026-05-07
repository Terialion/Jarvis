from __future__ import annotations

from ..schema import SearchQuery, SearchRun
from .base import BaseSearchProvider, ProviderSearchResponse


class DuckDuckGoSearchProvider(BaseSearchProvider):
    provider_name = "duckduckgo"
    engine_name = "duckduckgo"

    def search(self, query: SearchQuery) -> ProviderSearchResponse:
        return ProviderSearchResponse(
            run=SearchRun(
                provider=self.provider_name,
                engine=self.engine_name,
                query=query.query,
                ok=False,
                error="key_free_provider_not_enabled_in_phase13_default",
                result_count=0,
            ),
            results=[],
        )

