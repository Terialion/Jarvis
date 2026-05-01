from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .provider import LLMProvider


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    timeout_seconds: float = 60.0
    max_tokens: int = 4096

    @property
    def is_available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def redacted_summary(self) -> str:
        key_state = "present" if self.api_key else "missing"
        return (
            f"provider={self.provider or '<missing>'} "
            f"base_url={self.base_url or '<missing>'} "
            f"model={self.model or '<missing>'} "
            f"api_key={key_state}"
        )


def load_llm_provider_config() -> LLMProviderConfig:
    provider = (os.getenv("JARVIS_LLM_PROVIDER", "openai_compatible") or "").strip() or "openai_compatible"
    base_url = (os.getenv("JARVIS_LLM_BASE_URL", "") or "").strip().rstrip("/")
    api_key = (os.getenv("JARVIS_LLM_API_KEY", "") or "").strip()
    model = (os.getenv("JARVIS_LLM_MODEL", "") or "").strip()

    try:
        temperature = float((os.getenv("JARVIS_LLM_TEMPERATURE", "0.2") or "0.2").strip())
    except ValueError:
        temperature = 0.2
    try:
        timeout_seconds = float((os.getenv("JARVIS_LLM_TIMEOUT_SECONDS", "60") or "60").strip())
    except ValueError:
        timeout_seconds = 60.0
    try:
        max_tokens = int((os.getenv("JARVIS_LLM_MAX_TOKENS", "4096") or "4096").strip())
    except ValueError:
        max_tokens = 4096

    return LLMProviderConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
    )


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config
        self.model_name = config.model or "unknown"

    def complete(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        if not self.config.is_available:
            raise RuntimeError(f"LLM provider unavailable: {self.config.redacted_summary()}")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature == 0.2 else temperature,
            "max_tokens": self.config.max_tokens,
        }
        request_url = f"{self.config.base_url}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
            _write_provider_debug(
                {
                    "request_url": request_url,
                    "model": self.config.model,
                    "message_count": len(messages),
                    "system_prompt_length": len(system or ""),
                    "user_prompt_length": len(prompt or ""),
                    "temperature": payload["temperature"],
                    "max_tokens": self.config.max_tokens,
                    "http_status": int(exc.code),
                    "error": {"type": "HTTPError", "message": f"status={exc.code}"},
                }
            )
            raise RuntimeError(f"LLM HTTP error: status={exc.code}") from exc
        except urllib.error.URLError as exc:
            _write_provider_debug(
                {
                    "request_url": request_url,
                    "model": self.config.model,
                    "message_count": len(messages),
                    "system_prompt_length": len(system or ""),
                    "user_prompt_length": len(prompt or ""),
                    "temperature": payload["temperature"],
                    "max_tokens": self.config.max_tokens,
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
                    "message_count": len(messages),
                    "system_prompt_length": len(system or ""),
                    "user_prompt_length": len(prompt or ""),
                    "temperature": payload["temperature"],
                    "max_tokens": self.config.max_tokens,
                    "http_status": status,
                    "content_length": len(raw or ""),
                    "content_preview": str(raw or "")[:200],
                    "error": {"type": "JSONDecodeError", "message": "LLM response was not valid JSON"},
                }
            )
            raise RuntimeError("LLM response was not valid JSON") from exc
        return _extract_response_content(
            data=data,
            request_url=request_url,
            model=self.config.model,
            message_count=len(messages),
            system_prompt_length=len(system or ""),
            user_prompt_length=len(prompt or ""),
            temperature=payload["temperature"],
            max_tokens=self.config.max_tokens,
            http_status=status,
        )


def build_runtime_llm_provider(config: LLMProviderConfig | None = None) -> LLMProvider | None:
    cfg = config or load_llm_provider_config()
    if cfg.provider != "openai_compatible":
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
