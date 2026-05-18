from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    base_url: str
    api_key: str
    api_key_source: str
    base_url_source: str
    model_source: str
    temperature: float
    timeout_seconds: float
    max_tokens: int
    supports_native_tool_calling: bool = True
    deprecated_env_used: tuple[str, ...] = ()

    @property
    def is_real_provider(self) -> bool:
        return bool(self.api_key and self.provider != "fake")

    def masked_api_key(self) -> str:
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "****"
        return self.api_key[:4] + "****" + self.api_key[-4:]

    def redacted_summary(self) -> str:
        key_state = "present" if self.api_key else "missing"
        return (
            f"provider={self.provider or '<missing>'} "
            f"base_url={self.base_url or '<missing>'} "
            f"model={self.model or '<missing>'} "
            f"api_key={key_state}"
        )


PROVIDER_DEFAULTS: Dict[str, Dict[str, str]] = {
    "deepseek": {
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_API_BASE",
    },
    "openai": {
        "model": "gpt-4.1-mini",
        "base_url": "https://api.openai.com",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_API_BASE",
    },
    "openai_compatible": {
        "model": "",
        "base_url": "",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_API_BASE",
    },
    "openrouter": {
        "model": "openai/gpt-4.1-mini",
        "base_url": "https://openrouter.ai/api",
        "api_key_env": "OPENROUTER_API_KEY",
        "base_url_env": "OPENROUTER_BASE_URL",
    },
    "gemini": {
        "model": "gemini-2.5-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "base_url_env": "GEMINI_BASE_URL",
    },
    "minimax": {
        "model": "MiniMax-M2",
        "base_url": "https://api.minimax.io",
        "api_key_env": "MINIMAX_API_KEY",
        "base_url_env": "MINIMAX_BASE_URL",
    },
    "ollama": {
        "model": "llama3.1",
        "base_url": "https://ollama.com",
        "api_key_env": "OLLAMA_API_KEY",
        "base_url_env": "OLLAMA_BASE_URL",
    },
    "qwen": {
        "model": "qwen3.6-reasoner",
        "base_url": "https://api.llm.ustc.edu.cn",
        "api_key_env": "JARVIS_LLM_API_KEY",
        "base_url_env": "JARVIS_LLM_BASE_URL",
        "supports_native_tool_calling": "false",
    },
    "custom": {
        "model": "",
        "base_url": "",
        "api_key_env": "CUSTOM_LLM_API_KEY",
        "base_url_env": "CUSTOM_LLM_BASE_URL",
    },
    "fake": {
        "model": "fake-agent-v0",
        "base_url": "",
        "api_key_env": "",
        "base_url_env": "",
    },
}


LEGACY_ENV_ALIASES: Dict[str, tuple[str, ...]] = {
    "deepseek.api_key": ("LLM_DEEPSEEK_API_KEY", "JARVIS_LLM_DEEPSEEK_API_KEY"),
    "deepseek.base_url": ("LLM_DEEPSEEK_API_BASE", "JARVIS_LLM_DEEPSEEK_API_BASE"),
    "openai.api_key": ("LLM_OPENAI_API_KEY", "JARVIS_LLM_OPENAI_API_KEY"),
    "openai.base_url": ("LLM_OPENAI_API_BASE", "JARVIS_LLM_OPENAI_API_BASE"),
    "openai_compatible.api_key": ("LLM_OPENAI_API_KEY", "JARVIS_LLM_OPENAI_API_KEY"),
    "openai_compatible.base_url": ("LLM_OPENAI_API_BASE", "JARVIS_LLM_OPENAI_API_BASE"),
}


def load_dotenv(path: str | Path = ".env", *, override: bool = False) -> bool:
    env_path = Path(path)
    if not env_path.exists():
        return False
    try:
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value and len(value) >= 2 and (
                (value.startswith('"') and value.endswith('"'))
                or (value.startswith("'") and value.endswith("'"))
            ):
                value = value[1:-1]
            if override or not os.environ.get(key):
                os.environ[key] = value
    except Exception:
        return False
    return True


def _first_env(names: Iterable[str]) -> tuple[str, str]:
    for name in names:
        if not name:
            continue
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip(), name
    return "", ""


def _collect_present_env(names: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for name in names:
        if not name:
            continue
        val = os.environ.get(name)
        if val and val.strip():
            out.append(name)
    return tuple(out)


def _warn_deprecated(used_names: Iterable[str]) -> None:
    for name in used_names:
        warnings.warn(
            f"Deprecated env var {name} is set. "
            "Use JARVIS_LLM_API_KEY / JARVIS_LLM_BASE_URL or provider-native env names instead.",
            UserWarning,
            stacklevel=3,
        )


def normalize_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            value = value.rstrip("/")
    return value


def load_llm_config(*, dotenv_path: str | Path = ".env") -> LLMConfig:
    disable_dotenv = str(os.environ.get("JARVIS_LLM_DISABLE_DOTENV", "")).strip().lower() in {"1", "true", "yes", "on"}
    if dotenv_path and not disable_dotenv and "PYTEST_CURRENT_TEST" not in os.environ:
        load_dotenv(dotenv_path, override=False)

    provider = (
        os.environ.get("JARVIS_LLM_PROVIDER")
        or os.environ.get("LLM_PROVIDER")
        or os.environ.get("JARVIS_MODEL_PROVIDER")
        or "openai_compatible"
    ).strip().lower()

    defaults = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["custom"])

    all_legacy = []
    for names in LEGACY_ENV_ALIASES.values():
        all_legacy.extend(list(names))
    deprecated_env_used = _collect_present_env(all_legacy)
    if deprecated_env_used:
        _warn_deprecated(deprecated_env_used)

    model, model_source = _first_env(("JARVIS_LLM_MODEL", "JARVIS_MODEL", "OPENAI_MODEL", "DEEPSEEK_MODEL"))
    if not model:
        model = defaults.get("model", "")
        model_source = f"default:{provider}"

    base_url, base_url_source = _first_env(("JARVIS_LLM_BASE_URL", defaults.get("base_url_env", "")))
    if not base_url:
        legacy_base = LEGACY_ENV_ALIASES.get(f"{provider}.base_url", ())
        base_url, base_url_source = _first_env(legacy_base)
    if not base_url:
        base_url = defaults.get("base_url", "")
        base_url_source = f"default:{provider}"
    base_url = normalize_base_url(base_url)

    api_key, api_key_source = _first_env(("JARVIS_LLM_API_KEY", defaults.get("api_key_env", "")))
    if not api_key and provider == "gemini":
        api_key, api_key_source = _first_env(("GOOGLE_API_KEY",))
    if not api_key:
        legacy_key = LEGACY_ENV_ALIASES.get(f"{provider}.api_key", ())
        api_key, api_key_source = _first_env(legacy_key)

    if provider == "fake":
        api_key = ""
        api_key_source = "none"

    supports_native_tool_calling = defaults.get("supports_native_tool_calling", "true").strip().lower() not in {"false", "0", "no", "off"}

    # ── Resolve from ConfigManager (single source of truth) ──
    # ConfigManager priority: env var > config file > schema default.
    # Falls back to hardcoded env reads only when ConfigManager is unavailable.
    _cfg_temperature: float | None = None
    _cfg_timeout: float | None = None
    _cfg_max_tokens: int | None = None

    try:
        from ...config.manager import get_config  # type: ignore[import-not-found]

        cfg = get_config()
        if not model or model_source.startswith("default"):
            cfg_model = cfg.get("llm.model")
            if cfg_model and cfg_model != "deepseek-v4-pro":
                model = str(cfg_model)
                model_source = "config_file"
        if not base_url or base_url_source.startswith("default"):
            cfg_base = cfg.get("llm.base_url")
            if cfg_base:
                base_url = normalize_base_url(str(cfg_base))
                base_url_source = "config_file"
        if not api_key or api_key_source.startswith("missing"):
            cfg_key = cfg.get("llm.api_key")
            if cfg_key:
                api_key = str(cfg_key)
                api_key_source = "config_file"

        # Read runtime parameters via ConfigManager so config file
        # and schema defaults are the single source of truth.
        _cfg_temperature = float(cfg.get("llm.temperature") or 0)
        _cfg_timeout = float(cfg.get("llm.timeout_seconds") or 0)
        _cfg_max_tokens = int(cfg.get("llm.max_tokens") or 0)
    except Exception:
        pass  # ConfigManager not initialized in non-CLI contexts

    # Resolve: ConfigManager first, then env var, then hardcoded last resort.
    # ConfigManager.get() already checked env vars, but when ConfigManager is
    # unavailable we read env vars directly as fallback.
    if _cfg_temperature is not None and _cfg_temperature > 0:
        temperature = _cfg_temperature
    else:
        try:
            temperature = float((os.environ.get("JARVIS_LLM_TEMPERATURE", "0.2") or "0.2").strip())
        except ValueError:
            temperature = 0.2

    if _cfg_timeout is not None and _cfg_timeout > 0:
        timeout_seconds = _cfg_timeout
    else:
        try:
            timeout_seconds = float((os.environ.get("JARVIS_LLM_TIMEOUT_SECONDS", "300") or "300").strip())
        except ValueError:
            timeout_seconds = 300.0

    if _cfg_max_tokens is not None and _cfg_max_tokens > 0:
        max_tokens = _cfg_max_tokens
    else:
        try:
            max_tokens = int((os.environ.get("JARVIS_LLM_MAX_TOKENS", "32768") or "32768").strip())
        except ValueError:
            max_tokens = 32768

    return LLMConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
        api_key_source=api_key_source or "missing",
        base_url_source=base_url_source or "missing",
        model_source=model_source or "missing",
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        supports_native_tool_calling=supports_native_tool_calling,
        deprecated_env_used=tuple(sorted(set(deprecated_env_used))),
    )
