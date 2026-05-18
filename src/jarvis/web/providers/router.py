from __future__ import annotations

import os

from .base import BaseSearchProvider
from .bing import BingSearchProvider
from .brave import BraveSearchProvider
from .duckduckgo import DuckDuckGoSearchProvider
from .fake import FakeSearchProvider
from .tavily import TavilySearchProvider


def _vault_get(key: str) -> str | None:
    try:
        from jarvis.config.vault import get_vault
        return get_vault().get(key) or None
    except Exception:
        return None


def _prefer_live_provider() -> str:
    """Pick the best available live provider based on configured API keys."""
    if os.environ.get("TAVILY_API_KEY", "").strip() or _vault_get("search.tavily_api_key"):
        return "tavily"
    if os.environ.get("BRAVE_API_KEY", "").strip() or _vault_get("search.brave_api_key"):
        return "brave"
    return "bing"


class ProviderRouter:
    def __init__(self, *, default_provider: str = "fake") -> None:
        self.default_provider = default_provider
        self._providers: dict[str, BaseSearchProvider] = {
            "fake": FakeSearchProvider(),
            "brave": BraveSearchProvider(),
            "duckduckgo": DuckDuckGoSearchProvider(),
            "bing": BingSearchProvider(),
            "tavily": TavilySearchProvider(),
        }

    def resolve(self, provider: str | None, *, allow_live: bool = False) -> BaseSearchProvider:
        requested = str(provider or self.default_provider or "fake").strip().lower()
        if requested == "auto":
            if not allow_live:
                return self._providers["fake"]
            best = _prefer_live_provider()
            return self._providers[best]
        return self._providers.get(requested, self._providers["fake"])

