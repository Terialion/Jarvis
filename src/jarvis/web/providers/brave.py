from __future__ import annotations

from ..schema import SearchQuery, SearchRun
from .base import BaseSearchProvider, ProviderSearchResponse


class BraveSearchProvider(BaseSearchProvider):
    provider_name = "brave"
    engine_name = "brave"

    def search(self, query: SearchQuery) -> ProviderSearchResponse:
        return ProviderSearchResponse(
            run=SearchRun(
                provider=self.provider_name,
                engine=self.engine_name,
                query=query.query,
                ok=False,
                error="provider_not_configured",
                result_count=0,
            ),
            results=[],
        )

