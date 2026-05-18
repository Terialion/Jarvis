"""Brave Search API provider — requires BRAVE_API_KEY env var or vault entry.

Free tier: 2,000 queries/month. Sign up at https://brave.com/search/api/
"""

from __future__ import annotations

import json
import os
import urllib.request

from ..schema import SearchQuery, SearchResult, SearchRun
from .base import BaseSearchProvider, ProviderSearchResponse

_BRAVE_WEB_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_USER_AGENT = "JarvisAgent/0.22 (brave-search; +https://github.com/user/jarvis)"


class BraveSearchProvider(BaseSearchProvider):
    provider_name = "brave"
    engine_name = "brave"

    @staticmethod
    def _get_api_key() -> str | None:
        key = os.environ.get("BRAVE_API_KEY")
        if key:
            return key.strip() or None
        try:
            from jarvis.config.vault import get_vault
            return get_vault().get("search.brave_api_key") or None
        except Exception:
            return None

    def search(self, query: SearchQuery) -> ProviderSearchResponse:
        api_key = self._get_api_key()
        if not api_key:
            return ProviderSearchResponse(
                run=SearchRun(
                    provider=self.provider_name,
                    engine=self.engine_name,
                    query=query.query,
                    ok=False,
                    error="provider_not_configured: set BRAVE_API_KEY env var or store via vault",
                    result_count=0,
                ),
                results=[],
            )

        top_k = max(1, min(int(query.top_k or 5), 10))

        params = [
            ("q", str(query.query)),
            ("count", str(top_k)),
        ]
        if query.freshness:
            params.append(("freshness", query.freshness))

        query_string = urllib.parse.urlencode(params)
        req_url = f"{_BRAVE_WEB_ENDPOINT}?{query_string}"
        req = urllib.request.Request(
            req_url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
                "User-Agent": _BRAVE_USER_AGENT,
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return ProviderSearchResponse(
                run=SearchRun(
                    provider=self.provider_name,
                    engine=self.engine_name,
                    query=query.query,
                    ok=False,
                    error=str(exc),
                    result_count=0,
                ),
                results=[],
            )

        raw_results = data.get("web", {}).get("results", []) if isinstance(data, dict) else []
        results: list[SearchResult] = []
        for i, entry in enumerate(raw_results):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "")
            url = str(entry.get("url") or "")
            snippet = str(entry.get("description") or "")
            if not title or not url:
                continue
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=snippet[:300],
                rank=i + 1,
                source_type="web",
                provider="brave",
                engine="brave",
            ))

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
