from __future__ import annotations

from src.jarvis.web.providers.registry import SearchProviderRegistry


def test_registry_resolves_default_fake_provider():
    registry = SearchProviderRegistry.default()
    provider = registry.resolve("auto", allow_live=False)
    assert provider.provider_name == "fake"

