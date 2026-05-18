"""Provider/model metadata registry for runtime switching."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    base_url: str
    api_key_env: str
    models: tuple[str, ...]
    supports_native_tool_calling: bool = True


MODEL_REGISTRY: dict[str, ProviderInfo] = {
    "deepseek": ProviderInfo(
        name="deepseek",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        models=("deepseek-v4-pro", "deepseek-v4-flash", "deepseek-reasoner"),
    ),
    "openai": ProviderInfo(
        name="openai",
        base_url="https://api.openai.com",
        api_key_env="OPENAI_API_KEY",
        models=("gpt-4.1-mini", "gpt-4.1", "gpt-4.1-nano"),
    ),
    "openai_compatible": ProviderInfo(
        name="openai_compatible",
        base_url="",
        api_key_env="OPENAI_API_KEY",
        models=(),
    ),
    "openrouter": ProviderInfo(
        name="openrouter",
        base_url="https://openrouter.ai/api",
        api_key_env="OPENROUTER_API_KEY",
        models=("openai/gpt-4.1-mini", "openai/gpt-4.1", "anthropic/claude-sonnet-4-20250514"),
    ),
    "gemini": ProviderInfo(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GEMINI_API_KEY",
        models=("gemini-2.5-flash", "gemini-2.5-pro"),
    ),
    "minimax": ProviderInfo(
        name="minimax",
        base_url="https://api.minimax.io",
        api_key_env="MINIMAX_API_KEY",
        models=("MiniMax-M2",),
    ),
    "ollama": ProviderInfo(
        name="ollama",
        base_url="https://ollama.com",
        api_key_env="OLLAMA_API_KEY",
        models=("llama3.1",),
    ),
    "qwen": ProviderInfo(
        name="qwen",
        base_url="https://api.llm.ustc.edu.cn",
        api_key_env="JARVIS_LLM_API_KEY",
        models=("qwen3.6-reasoner", "qwen3.6-chat"),
        supports_native_tool_calling=False,
    ),
    "custom": ProviderInfo(
        name="custom",
        base_url="",
        api_key_env="CUSTOM_LLM_API_KEY",
        models=(),
    ),
}


def get_provider_info(name: str) -> ProviderInfo | None:
    return MODEL_REGISTRY.get(name.lower())


def list_providers() -> list[str]:
    return list(MODEL_REGISTRY.keys())


def list_models(provider: str) -> list[str]:
    info = MODEL_REGISTRY.get(provider.lower())
    return list(info.models) if info else []


def get_default_model(provider: str) -> str:
    info = MODEL_REGISTRY.get(provider.lower())
    return info.models[0] if info and info.models else ""
