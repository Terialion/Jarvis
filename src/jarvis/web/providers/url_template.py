from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass
class UrlTemplateResult:
    engine: str
    query_url: str


URL_TEMPLATES = {
    "duckduckgo": "https://duckduckgo.com/html/?q={query}",
    "brave": "https://search.brave.com/search?q={query}",
    "google": "https://www.google.com/search?q={query}",
}


def build_query_url(engine: str, query: str) -> UrlTemplateResult:
    template = URL_TEMPLATES.get(engine, URL_TEMPLATES["duckduckgo"])
    return UrlTemplateResult(engine=engine, query_url=template.format(query=quote_plus(str(query or "").strip())))

