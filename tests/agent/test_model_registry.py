"""Unit tests for model_registry."""
from __future__ import annotations

from src.jarvis.agent.model_registry import (
    get_default_model,
    get_provider_info,
    list_models,
    list_providers,
)


def test_list_providers_includes_all_known():
    providers = list_providers()
    assert "deepseek" in providers
    assert "openai" in providers
    assert "qwen" in providers
    assert "gemini" in providers
    assert "custom" in providers


def test_list_models_for_deepseek():
    models = list_models("deepseek")
    assert "deepseek-v4-pro" in models
    assert "deepseek-v4-flash" in models
    assert "deepseek-reasoner" in models


def test_list_models_case_insensitive():
    assert list_models("DeepSeek") == list_models("deepseek")


def test_list_models_unknown_provider_returns_empty():
    assert list_models("nonexistent") == []


def test_get_default_model():
    assert get_default_model("deepseek") == "deepseek-v4-pro"
    assert get_default_model("qwen") == "qwen3.6-reasoner"


def test_get_default_model_unknown_returns_empty():
    assert get_default_model("nonexistent") == ""


def test_get_provider_info_deepseek():
    info = get_provider_info("deepseek")
    assert info is not None
    assert info.base_url == "https://api.deepseek.com"
    assert info.api_key_env == "DEEPSEEK_API_KEY"
    assert info.supports_native_tool_calling is True


def test_get_provider_info_qwen_no_native_tools():
    info = get_provider_info("qwen")
    assert info is not None
    assert info.supports_native_tool_calling is False


def test_get_provider_info_unknown_returns_none():
    assert get_provider_info("nonexistent") is None
