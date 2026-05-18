"""DuckDuckGo search provider — free, no API key required.

Uses DuckDuckGo Lite (text-only HTML) for reliable, lightweight parsing.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

from ..schema import SearchQuery, SearchResult, SearchRun
from .base import BaseSearchProvider, ProviderSearchResponse

_LITE_URL = "https://lite.duckduckgo.com/lite/"
_USER_AGENT = "JarvisAgent/0.21 (search; +https://github.com/user/jarvis)"


def _parse_lite_html(html: str, query: str, top_k: int) -> list[SearchResult]:
    """Extract result rows from DuckDuckGo Lite HTML."""
    results: list[SearchResult] = []

    # Each result row: <a href="URL" ...>Title</a> ... <span class="link-text">snippet</span>
    link_pattern = re.compile(
        r'<a\s[^>]*href="([^"]+)"[^>]*class="[^"]*result-link[^"]*"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_pattern = re.compile(
        r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
        re.DOTALL | re.IGNORECASE,
    )

    links = link_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i in range(min(len(links), top_k)):
        href = links[i][0].strip()
        title = re.sub(r"<[^>]+>", "", links[i][1]).strip()
        snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
        url = urllib.parse.unquote(href) if href.startswith("//duckduckgo.com/l/?uddg=") else href
        # Decode DuckDuckGo redirect URLs
        uddg_match = re.search(r"uddg=([^&]+)", url)
        if uddg_match:
            url = urllib.parse.unquote(uddg_match.group(1))

        if title and url:
            results.append(SearchResult(
                title=title,
                url=url,
                snippet=snippet or title,
                rank=i + 1,
                source_type="web",
                provider="duckduckgo",
                engine="duckduckgo",
            ))

    return results


class DuckDuckGoSearchProvider(BaseSearchProvider):
    provider_name = "duckduckgo"
    engine_name = "duckduckgo"

    def search(self, query: SearchQuery) -> ProviderSearchResponse:
        params = urllib.parse.urlencode({"q": str(query.query), "t": "jarvis"})
        req_url = f"{_LITE_URL}?{params}"
        req = urllib.request.Request(req_url, headers={"User-Agent": _USER_AGENT})

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
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
        results = _parse_lite_html(html, query.query, top_k)

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
