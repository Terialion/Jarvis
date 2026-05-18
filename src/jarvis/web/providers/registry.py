from __future__ import annotations

from dataclasses import dataclass

from .base import BaseSearchProvider
from .router import ProviderRouter


@dataclass
class SearchProviderRegistry:
    """Small compatibility registry layered on top of ProviderRouter."""

    router: ProviderRouter

    @classmethod
    def default(cls) -> "SearchProviderRegistry":
        return cls(router=ProviderRouter())

    def resolve(self, provider: str | None, *, allow_live: bool = False) -> BaseSearchProvider:
        return self.router.resolve(provider, allow_live=allow_live)

