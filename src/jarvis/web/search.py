from __future__ import annotations

from .cache import WebCache, make_search_cache_key
from .providers.base import ProviderSearchResponse
from .providers.router import ProviderRouter
from .schema import SearchQuery, WebToolResult


def run_web_search(query: SearchQuery, *, router: ProviderRouter | None = None, cache: WebCache | None = None, allow_live: bool = False) -> WebToolResult:
    router = router or ProviderRouter()
    cache = cache or WebCache()
    provider = router.resolve(query.provider, allow_live=allow_live)
    key = make_search_cache_key(provider.provider_name, provider.engine_name, query.query, query.top_k, query.freshness, query.site)
    cached = cache.get_search(key)
    if cached is not None:
        return cached
    try:
        response: ProviderSearchResponse = provider.search(query)
    except Exception as exc:
        result = WebToolResult(
            ok=False,
            error=str(exc),
            runs=[{"provider": getattr(provider, "provider_name", "unknown"), "engine": getattr(provider, "engine_name", "unknown"), "query": query.query, "ok": False, "error": str(exc), "result_count": 0}],
            results=[],
        )
        cache.set_search(key, result.to_dict())
        return result

    result = WebToolResult(
        ok=response.run.ok,
        error=response.run.error,
        runs=[response.run.to_dict()],
        results=[row.to_dict() for row in response.results],
    )
    cache.set_search(key, result.to_dict())
    return result

