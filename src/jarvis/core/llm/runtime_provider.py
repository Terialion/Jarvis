from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import LLMConfig, load_llm_config
from .provider import LLMProvider

_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def _sanitize_surrogates(obj: Any) -> Any:
    """Recursively replace lone surrogates (invalid UTF-8) in all strings."""
    if isinstance(obj, str):
        return _SURROGATE_RE.sub("�", obj)
    if isinstance(obj, dict):
        return {k: _sanitize_surrogates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_surrogates(v) for v in obj]
    return obj

OPENAI_COMPATIBLE_PROVIDERS = {
    "openai_compatible",
    "openai",
    "deepseek",
    "openrouter",
    "gemini",
    "minimax",
    "ollama",
    "qwen",
    "custom",
}


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    timeout_seconds: float = 60.0
    max_tokens: int = 4096
    api_key_source: str = "missing"
    base_url_source: str = "missing"
    model_source: str = "missing"
    deprecated_env_used: tuple[str, ...] = ()
    supports_native_tool_calling: bool = True

    @property
    def is_available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    @property
    def supports_runtime(self) -> bool:
        return self.provider in OPENAI_COMPATIBLE_PROVIDERS

    def redacted_summary(self) -> str:
        key_state = "present" if self.api_key else "missing"
        return (
            f"provider={self.provider or '<missing>'} "
            f"base_url={self.base_url or '<missing>'} "
            f"model={self.model or '<missing>'} "
            f"api_key={key_state}"
        )

    @classmethod
    def from_llm_config(cls, cfg: LLMConfig) -> "LLMProviderConfig":
        return cls(
            provider=cfg.provider,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            temperature=cfg.temperature,
            timeout_seconds=cfg.timeout_seconds,
            max_tokens=cfg.max_tokens,
            api_key_source=cfg.api_key_source,
            base_url_source=cfg.base_url_source,
            model_source=cfg.model_source,
            deprecated_env_used=cfg.deprecated_env_used,
            supports_native_tool_calling=cfg.supports_native_tool_calling,
        )


def load_llm_provider_config() -> LLMProviderConfig:
    return LLMProviderConfig.from_llm_config(load_llm_config())


def _build_chat_completions_url(base_url: str) -> str:
    root = (base_url or "").rstrip("/")
    if not root:
        return "/v1/chat/completions"
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config
        self.model_name = config.model or "unknown"
        self.supports_native_tool_calling = config.supports_native_tool_calling

    def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> dict[str, Any]:
        if not self.config.is_available:
            raise RuntimeError(f"LLM provider unavailable: {self.config.redacted_summary()}")

        request_messages = list(messages or [])
        if system:
            request_messages = [{"role": "system", "content": system}] + request_messages

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": request_messages,
            "temperature": self.config.temperature if temperature == 0.2 else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else int(max_tokens),
        }
        if tools and self.supports_native_tool_calling:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        request_url = _build_chat_completions_url(self.config.base_url)
        body = json.dumps(_sanitize_surrogates(payload), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            request_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            try:
                resp_body = exc.read().decode("utf-8", errors="replace")[:1000]
            except Exception:
                resp_body = "(unable to read response body)"
            _write_provider_debug(
                {
                    "request_url": request_url,
                    "model": self.config.model,
                    "message_count": len(request_messages),
                    "system_prompt_length": len(system or ""),
                    "user_prompt_length": len(str(request_messages[-1].get("content") or "")) if request_messages else 0,
                    "temperature": payload["temperature"],
                    "max_tokens": payload["max_tokens"],
                    "http_status": int(exc.code),
                    "error": {"type": "HTTPError", "message": f"status={exc.code}", "body": resp_body},
                }
            )
            raise RuntimeError(f"LLM HTTP error: status={exc.code} body={resp_body[:200]}") from exc
        except urllib.error.URLError as exc:
            _write_provider_debug(
                {
                    "request_url": request_url,
                    "model": self.config.model,
                    "message_count": len(request_messages),
                    "system_prompt_length": len(system or ""),
                    "user_prompt_length": len(str(request_messages[-1].get("content") or "")) if request_messages else 0,
                    "temperature": payload["temperature"],
                    "max_tokens": payload["max_tokens"],
                    "error": {"type": "URLError", "message": str(exc.reason)},
                }
            )
            raise RuntimeError(f"LLM network error: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            _write_provider_debug(
                {
                    "request_url": request_url,
                    "model": self.config.model,
                    "message_count": len(request_messages),
                    "system_prompt_length": len(system or ""),
                    "user_prompt_length": len(str(request_messages[-1].get("content") or "")) if request_messages else 0,
                    "temperature": payload["temperature"],
                    "max_tokens": payload["max_tokens"],
                    "http_status": status,
                    "content_length": len(raw or ""),
                    "content_preview": str(raw or "")[:200],
                    "error": {"type": "JSONDecodeError", "message": "LLM response was not valid JSON"},
                }
            )
            raise RuntimeError("LLM response was not valid JSON") from exc
        if isinstance(data.get("error"), dict):
            err = data["error"]
            err_type = str(err.get("type") or "provider_error")
            err_message = str(err.get("message") or "unknown error")
            _write_provider_debug(
                {
                    "request_url": request_url,
                    "model": self.config.model,
                    "message_count": len(request_messages),
                    "http_status": status,
                    "error": {"type": err_type, "message": err_message[:300]},
                }
            )
            raise RuntimeError(f"LLM provider error: type={err_type} message={err_message}")
        return data

    def chat_completion_stream(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        system: str | None = None,
    ) -> Any:
        """Stream chat completion via SSE and yield parsed chunk dicts.

        Each yielded dict is the JSON-decoded ``data:`` line of a single SSE chunk.
        The caller must check ``choices[0].delta`` / ``choices[0].finish_reason``
        and aggregate across chunks.
        """
        if not self.config.is_available:
            raise RuntimeError(f"LLM provider unavailable: {self.config.redacted_summary()}")

        request_messages = list(messages or [])
        if system:
            request_messages = [{"role": "system", "content": system}] + request_messages

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": request_messages,
            "temperature": self.config.temperature if temperature == 0.2 else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else int(max_tokens),
            "stream": True,
        }
        if tools and self.supports_native_tool_calling:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        request_url = _build_chat_completions_url(self.config.base_url)
        body = json.dumps(_sanitize_surrogates(payload), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            request_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self.config.timeout_seconds)
        except urllib.error.HTTPError as exc:
            try:
                resp_body = exc.read().decode("utf-8", errors="replace")[:1000]
            except Exception:
                resp_body = "(unable to read response body)"
            raise RuntimeError(f"LLM HTTP error: status={exc.code} body={resp_body[:200]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM network error: {exc.reason}") from exc

        try:
            for line in resp:
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                if line_str.startswith("data: "):
                    data_str = line_str[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(chunk.get("error"), dict):
                        err = chunk["error"]
                        raise RuntimeError(
                            f"LLM provider error: type={err.get('type', 'provider_error')} "
                            f"message={err.get('message', 'unknown')}"
                        )
                    yield chunk
        finally:
            resp.close()

    def complete(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        messages = [{"role": "user", "content": prompt}]
        data = self.chat_completion(
            messages=messages,
            tools=None,
            temperature=temperature,
            max_tokens=self.config.max_tokens,
            system=system,
        )
        status = 200
        return _extract_response_content(
            data=data,
            request_url=_build_chat_completions_url(self.config.base_url),
            model=self.config.model,
            message_count=1 + (1 if system else 0),
            system_prompt_length=len(system or ""),
            user_prompt_length=len(prompt or ""),
            temperature=self.config.temperature if temperature == 0.2 else temperature,
            max_tokens=self.config.max_tokens,
            http_status=status,
        )


def build_runtime_llm_provider(config: LLMProviderConfig | None = None) -> LLMProvider | None:
    cfg = config or load_llm_provider_config()
    if not cfg.supports_runtime:
        return None
    if not cfg.is_available:
        return None
    return OpenAICompatibleProvider(cfg)


def _extract_response_content(
    *,
    data: dict[str, Any],
    request_url: str,
    model: str,
    message_count: int,
    system_prompt_length: int,
    user_prompt_length: int,
    temperature: float,
    max_tokens: int,
    http_status: int,
) -> str:
    debug: dict[str, Any] = {
        "request_url": request_url,
        "model": model,
        "message_count": message_count,
        "system_prompt_length": system_prompt_length,
        "user_prompt_length": user_prompt_length,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "http_status": http_status,
        "response_json_keys": sorted(list(data.keys())),
    }

    if isinstance(data.get("error"), dict):
        err = data["error"]
        err_type = str(err.get("type") or "provider_error")
        err_message = str(err.get("message") or "unknown error")
        debug["error"] = {"type": err_type, "message": err_message[:300]}
        _write_provider_debug(debug)
        raise RuntimeError(f"LLM provider error: type={err_type} message={err_message}")

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        debug["choices_count"] = 0
        _write_provider_debug(debug)
        raise RuntimeError("LLM response missing choices")

    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}

    finish_reason = str(first.get("finish_reason") or "")
    content = message.get("content")
    content_text = "" if content is None else str(content)
    message_keys = sorted(list(message.keys()))
    tool_calls = message.get("tool_calls")
    reasoning_content = message.get("reasoning_content")
    reasoning = message.get("reasoning")
    reasoning_text = message.get("reasoning_text")

    debug.update(
        {
            "choices_count": len(choices),
            "choice0_keys": sorted(list(first.keys())) if isinstance(first, dict) else [],
            "message_keys": message_keys,
            "content_length": len(content_text),
            "content_preview": content_text[:200],
            "finish_reason": finish_reason,
            "usage": data.get("usage"),
            "reasoning_content_present": bool(reasoning_content),
            "reasoning_content_length": len(str(reasoning_content or "")),
            "reasoning_present": bool(reasoning),
            "reasoning_text_present": bool(reasoning_text),
            "tool_calls_present": isinstance(tool_calls, list) and len(tool_calls) > 0,
            "tool_calls_count": len(tool_calls) if isinstance(tool_calls, list) else 0,
        }
    )

    _write_provider_debug(debug)

    if content_text.strip():
        return content_text

    if isinstance(tool_calls, list) and tool_calls:
        raise RuntimeError(
            "LLM empty content: provider-native tool_calls returned; "
            "Jarvis expects JSON tool_plan in content"
        )

    if reasoning_content or reasoning or reasoning_text:
        raise RuntimeError(
            "LLM empty content: content_length=0 "
            f"reasoning_content_present={bool(reasoning_content)} finish_reason={finish_reason or '<none>'}"
        )

    raise RuntimeError(
        "LLM empty content: "
        f"finish_reason={finish_reason or '<none>'} "
        f"message_keys={','.join(message_keys) or '<none>'} content_length=0"
    )


def _write_provider_debug(payload: dict[str, Any]) -> None:
    if str(os.getenv("JARVIS_LLM_DEBUG", "")).strip() not in {"1", "true", "TRUE", "on", "ON"}:
        return
    try:
        out = Path("temp") / "llm_provider_debug_last.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return
