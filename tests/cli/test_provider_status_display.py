from __future__ import annotations

from jarvis import cli as cli_mod


def test_provider_status_available_without_key_leak(monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "super-secret-key")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "demo-model")

    class _Provider:
        pass

    monkeypatch.setattr(
        "src.jarvis.core.llm.runtime_provider.build_runtime_llm_provider",
        lambda *_a, **_k: _Provider(),
    )
    line, provider = cli_mod._build_provider_status_line()
    assert provider is not None
    assert "status=available" in line
    assert "LLM provider: openai_compatible" in line
    assert "api_key=present" in line
    assert "super-secret-key" not in line


def test_provider_status_unavailable_missing_api_key(monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.delenv("JARVIS_LLM_API_KEY", raising=False)
    monkeypatch.setenv("JARVIS_LLM_MODEL", "demo-model")
    line, provider = cli_mod._build_provider_status_line()
    assert provider is None
    assert "fallback mode enabled" in line
    assert "missing api_key" in line


def test_provider_status_unavailable_missing_model_and_base_url(monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.delenv("JARVIS_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "present")
    monkeypatch.delenv("JARVIS_LLM_MODEL", raising=False)
    line, provider = cli_mod._build_provider_status_line()
    assert provider is None
    assert "fallback mode enabled" in line
    assert "missing base_url,model" in line


def test_provider_status_unavailable_unknown_provider(monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "mystery")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "present")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "demo-model")
    line, provider = cli_mod._build_provider_status_line()
    assert provider is None
    assert "fallback mode enabled" in line
    assert "unknown provider=mystery" in line
