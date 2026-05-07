from __future__ import annotations

from .base import BaseSearchProvider
from .brave import BraveSearchProvider
from .duckduckgo import DuckDuckGoSearchProvider
from .fake import FakeSearchProvider


class ProviderRouter:
    def __init__(self, *, default_provider: str = "fake") -> None:
        self.default_provider = default_provider
        self._providers: dict[str, BaseSearchProvider] = {
            "fake": FakeSearchProvider(),
            "brave": BraveSearchProvider(),
            "duckduckgo": DuckDuckGoSearchProvider(),
        }

    def resolve(self, provider: str | None, *, allow_live: bool = False) -> BaseSearchProvider:
        requested = str(provider or self.default_provider or "fake").strip().lower()
        if requested == "auto":
            return self._providers["brave"] if allow_live else self._providers["fake"]
        return self._providers.get(requested, self._providers["fake"])

