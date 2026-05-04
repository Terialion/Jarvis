from __future__ import annotations

import warnings

from src.jarvis.core.llm.config import load_llm_config, normalize_base_url


def _clear_llm_env(monkeypatch):
    keys = [
        "JARVIS_LLM_PROVIDER",
        "JARVIS_LLM_MODEL",
        "JARVIS_LLM_BASE_URL",
        "JARVIS_LLM_API_KEY",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_BASE",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "OPENROUTER_API_KEY",
        "OPENROUTER_BASE_URL",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_BASE_URL",
        "MINIMAX_API_KEY",
        "MINIMAX_BASE_URL",
        "OLLAMA_API_KEY",
        "OLLAMA_BASE_URL",
        "LLM_DEEPSEEK_API_KEY",
        "JARVIS_LLM_DEEPSEEK_API_KEY",
        "LLM_OPENAI_API_KEY",
        "JARVIS_LLM_OPENAI_API_KEY",
        "LLM_OPENAI_API_BASE",
        "JARVIS_LLM_OPENAI_API_BASE",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_canonical_api_key_has_highest_precedence(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "canonical-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "native-key")
    cfg = load_llm_config()
    assert cfg.api_key == "canonical-key"
    assert cfg.api_key_source == "JARVIS_LLM_API_KEY"


def test_provider_native_fallback_applies(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "native-key")
    monkeypatch.setenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    cfg = load_llm_config()
    assert cfg.api_key == "native-key"
    assert cfg.api_key_source == "DEEPSEEK_API_KEY"
    assert cfg.base_url == "https://api.deepseek.com"
    assert cfg.base_url_source == "DEEPSEEK_API_BASE"


def test_legacy_alias_applies_and_is_reported(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_DEEPSEEK_API_KEY", "legacy-key")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = load_llm_config()
    assert cfg.api_key == "legacy-key"
    assert "LLM_DEEPSEEK_API_KEY" in cfg.deprecated_env_used
    assert any("Deprecated env var LLM_DEEPSEEK_API_KEY" in str(item.message) for item in caught)


def test_normalize_base_url_strips_chat_completion_suffix():
    assert normalize_base_url("https://api.deepseek.com/v1/chat/completions") == "https://api.deepseek.com"
    assert normalize_base_url("https://api.example.com/chat/completions") == "https://api.example.com"


def test_fake_provider_does_not_require_api_key(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "fake")
    cfg = load_llm_config()
    assert cfg.provider == "fake"
    assert cfg.api_key == ""
    assert cfg.is_real_provider is False


def test_masked_api_key_does_not_leak_full_value(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "sk-abcdefghijklmnopqrstuvwxyz")
    cfg = load_llm_config()
    masked = cfg.masked_api_key()
    assert masked
    assert "abcdefghijklmnopqrstuvwxyz" not in masked
    assert masked.startswith("sk-a")
    assert masked.endswith("wxyz")

