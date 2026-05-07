from __future__ import annotations

from ..fixtures import fake_search_rows_for_query
from ..schema import SearchQuery, SearchResult, SearchRun
from .base import BaseSearchProvider, ProviderSearchResponse


class FakeSearchProvider(BaseSearchProvider):
    provider_name = "fake"
    engine_name = "fake"

    def search(self, query: SearchQuery) -> ProviderSearchResponse:
        rows = fake_search_rows_for_query(query.query, site=query.site)
        results = [
            SearchResult(
                title=row["title"],
                url=row["url"],
                snippet=row["snippet"],
                rank=index + 1,
                source_type=str(row.get("source_type") or "unknown"),
                provider=self.provider_name,
                engine=self.engine_name,
            )
            for index, row in enumerate(rows[: max(1, int(query.top_k or 5))])
        ]
        return ProviderSearchResponse(
            run=SearchRun(
                provider=self.provider_name,
                engine=self.engine_name,
                query=query.query,
                ok=True,
                result_count=len(results),
            ),
            results=results,
        )

