"""Tavily Search API provider — AI-optimized search with structured results.

Free dev tier: 1,000 queries/month. Sign up at https://tavily.com/
"""

from __future__ import annotations

import json
import os
import urllib.request

from ..schema import SearchQuery, SearchResult, SearchRun
from .base import BaseSearchProvider, ProviderSearchResponse

_TAVILY_ENDPOINT = "https://api.tavily.com/search"
_USER_AGENT = "JarvisAgent/0.22 (tavily-search; +https://github.com/user/jarvis)"


class TavilySearchProvider(BaseSearchProvider):
    provider_name = "tavily"
    engine_name = "tavily"

    @staticmethod
    def _get_api_key() -> str | None:
        key = os.environ.get("TAVILY_API_KEY")
        if key:
            return key.strip() or None
        try:
            from jarvis.config.vault import get_vault
            return get_vault().get("search.tavily_api_key") or None
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
                    error="provider_not_configured: set TAVILY_API_KEY env var or store via vault",
                    result_count=0,
                ),
                results=[],
            )

        top_k = max(1, min(int(query.top_k or 5), 10))
        body = json.dumps({
            "api_key": api_key,
            "query": str(query.query),
            "search_depth": "basic",
            "max_results": top_k,
            "include_answer": "basic",
            "include_raw_content": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            _TAVILY_ENDPOINT,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": _USER_AGENT,
            },
            method="POST",
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

        raw_results = data.get("results", []) if isinstance(data, dict) else []
        results: list[SearchResult] = []
        for i, entry in enumerate(raw_results):
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title") or "")
            url = str(entry.get("url") or "")
            snippet = str(entry.get("content") or "")
            if not title or not url:
                continue
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=snippet[:300],
                rank=i + 1,
                source_type="web",
                provider="tavily",
                engine="tavily",
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
