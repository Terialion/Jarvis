"""Model client abstraction for AgentLoop."""

from __future__ import annotations

from typing import Protocol

from .types import ChatMessage, ModelResponse, ToolSpec, ToolCall


class ModelClient(Protocol):
    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> ModelResponse: ...


class MockModelClient:
    """Deterministic model for tests.

    responses may contain strings or ModelResponse objects. A string becomes final answer.
    """

    def __init__(self, responses: list[str | ModelResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> ModelResponse:
        self.calls.append(messages)
        if not self.responses:
            return ModelResponse(content="No more mock responses.", stop_reason="stop")
        item = self.responses.pop(0)
        return ModelResponse(content=item, stop_reason="stop") if isinstance(item, str) else item


class RuntimeModelClient:
    """Bridge to Jarvis existing LLM provider.

    Codex should wire this to `src.jarvis.core.llm.runtime_provider` if present.
    Keep MockModelClient tests passing before enabling real provider calls.
    """

    def __init__(self, provider) -> None:
        self.provider = provider

    def complete(self, messages: list[ChatMessage], tools: list[ToolSpec]) -> ModelResponse:
        # Implementation target:
        # 1. Convert ChatMessage to provider message format.
        # 2. Convert ToolSpec to provider tool schema if supported.
        # 3. Call provider.
        # 4. Parse native tool_calls into ToolCall.
        raise NotImplementedError("Wire to Jarvis runtime provider after core loop tests pass")
