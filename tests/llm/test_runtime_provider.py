from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from src.jarvis.core.llm.runtime_provider import (
    OpenAICompatibleProvider,
    build_runtime_llm_provider,
    load_llm_provider_config,
)


def test_load_config_and_redaction(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "secret")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    cfg = load_llm_provider_config()
    assert cfg.is_available is True
    summary = cfg.redacted_summary()
    assert "api_key=present" in summary
    assert "secret" not in summary


def test_build_runtime_provider_returns_none_when_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.delenv("JARVIS_LLM_API_KEY", raising=False)
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    assert build_runtime_llm_provider() is None


def test_build_runtime_provider_returns_none_for_unknown_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "unknown")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "secret")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    assert build_runtime_llm_provider() is None


def test_openai_compatible_http_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "secret")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    provider = OpenAICompatibleProvider(load_llm_provider_config())

    def _boom(*_args, **_kwargs):
        raise HTTPError(url="https://api.example.com", code=401, msg="unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("src.jarvis.core.llm.runtime_provider.urllib.request.urlopen", _boom)
    with pytest.raises(RuntimeError, match="LLM HTTP error: status=401"):
        provider.complete("hello")


def test_openai_compatible_malformed_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "secret")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    provider = OpenAICompatibleProvider(load_llm_provider_config())

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return json.dumps({"oops": 1}).encode("utf-8")

    monkeypatch.setattr("src.jarvis.core.llm.runtime_provider.urllib.request.urlopen", lambda *_a, **_k: _Resp())
    with pytest.raises(RuntimeError, match="missing choices"):
        provider.complete("hello")


def test_openai_compatible_empty_content_with_finish_reason(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "secret")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    provider = OpenAICompatibleProvider(load_llm_provider_config())

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return json.dumps(
                {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
            ).encode("utf-8")

    monkeypatch.setattr("src.jarvis.core.llm.runtime_provider.urllib.request.urlopen", lambda *_a, **_k: _Resp())
    with pytest.raises(RuntimeError, match="finish_reason=length"):
        provider.complete("hello")


def test_openai_compatible_empty_content_with_reasoning_content(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "secret")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    provider = OpenAICompatibleProvider(load_llm_provider_config())

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": "", "reasoning_content": "hidden"},
                        }
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr("src.jarvis.core.llm.runtime_provider.urllib.request.urlopen", lambda *_a, **_k: _Resp())
    with pytest.raises(RuntimeError, match="reasoning_content_present=True"):
        provider.complete("hello")


def test_openai_compatible_empty_content_with_native_tool_calls(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "secret")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    provider = OpenAICompatibleProvider(load_llm_provider_config())

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "content": "",
                                "tool_calls": [{"id": "x", "type": "function"}],
                            },
                        }
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr("src.jarvis.core.llm.runtime_provider.urllib.request.urlopen", lambda *_a, **_k: _Resp())
    with pytest.raises(RuntimeError, match="provider-native tool_calls returned"):
        provider.complete("hello")


def test_openai_compatible_provider_error_in_json_body(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("JARVIS_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("JARVIS_LLM_API_KEY", "secret")
    monkeypatch.setenv("JARVIS_LLM_MODEL", "model-x")
    provider = OpenAICompatibleProvider(load_llm_provider_config())

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def read(self):
            return json.dumps(
                {"error": {"type": "invalid_request_error", "message": "bad request"}}
            ).encode("utf-8")

    monkeypatch.setattr("src.jarvis.core.llm.runtime_provider.urllib.request.urlopen", lambda *_a, **_k: _Resp())
    with pytest.raises(RuntimeError, match="type=invalid_request_error"):
        provider.complete("hello")
