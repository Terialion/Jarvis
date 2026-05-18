"""Bing search provider — works in regions where DuckDuckGo is blocked."""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

from ..schema import SearchQuery, SearchResult, SearchRun
from .base import BaseSearchProvider, ProviderSearchResponse

_BING_URL = "https://www.bing.com/search"
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def _parse_bing_html(html: str, top_k: int) -> list[SearchResult]:
    """Extract search results from Bing's HTML using h2 > a + sibling <p>."""
    results: list[SearchResult] = []

    # Each result: <h2 ...><a href="URL" ...>Title</a></h2> ... <p ...>Snippet</p>
    h2_matches = re.findall(
        r'<h2[^>]*>\s*<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>\s*</h2>',
        html, re.DOTALL | re.IGNORECASE,
    )
    p_matches = re.findall(
        r'<p[^>]*class="[^"]*(?:b_linebreak|b_algoSlug|b_caption)[^"]*"[^>]*>(.*?)</p>',
        html, re.DOTALL | re.IGNORECASE,
    )

    for i, (url, title_html) in enumerate(h2_matches):
        if len(results) >= top_k:
            break
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        raw_snippet = re.sub(r"<[^>]+>", "", p_matches[i]).strip() if i < len(p_matches) else ""
        snippet = raw_snippet[:300] if raw_snippet else title

        if title and url:
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=snippet[:300],
                rank=len(results) + 1,
                source_type="web",
                provider="bing",
                engine="bing",
            ))

    return results


class BingSearchProvider(BaseSearchProvider):
    provider_name = "bing"
    engine_name = "bing"

    @staticmethod
    def _detect_market(query_text: str) -> str:
        """Pick market based on query language, not hardcoded locale."""
        has_cjk = any('一' <= c <= '鿿' or '぀' <= c <= 'ヿ' for c in query_text)
        return "zh-CN" if has_cjk else "en-US"

    def search(self, query: SearchQuery) -> ProviderSearchResponse:
        market = self._detect_market(str(query.query))
        params = urllib.parse.urlencode({
            "q": str(query.query),
            "count": str(max(1, int(query.top_k or 5)) + 2),
            "setmkt": market,
        })
        req_url = f"{_BING_URL}?{params}"
        req = urllib.request.Request(req_url, headers={"User-Agent": _USER_AGENT})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
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

        top_k = max(1, int(query.top_k or 5))
        results = _parse_bing_html(html, top_k)

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
