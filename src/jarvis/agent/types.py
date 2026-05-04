"""Core types for Jarvis AgentLoop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

MessageRole = Literal["system", "user", "assistant", "tool"]
AgentOutputType = Literal["answer", "tool_result", "clarification", "refusal", "partial", "error"]

_SENSITIVE_KEYWORDS = ("token", "secret", "api_key", "password", "authorization", "private_key")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k).lower()
            if any(tag in key for tag in _SENSITIVE_KEYWORDS):
                out[str(k)] = "***"
            else:
                out[str(k)] = _redact_value(v)
        return out
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


@dataclass
class ChatInput:
    text: str
    session_id: str | None = None
    project_id: str | None = None
    cwd: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class AgentTurn:
    turn_id: str
    session_id: str
    status: str
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    requires_approval: bool = False
    permissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    risk_level: str = "low"
    requires_approval: bool = False
    reason: str | None = None

    @classmethod
    def new(
        cls,
        *,
        name: str,
        arguments: dict[str, Any] | None = None,
        risk_level: str = "low",
        requires_approval: bool = False,
        reason: str | None = None,
    ) -> "ToolCall":
        return cls(
            id=f"call_{uuid4().hex[:12]}",
            name=name,
            arguments=dict(arguments or {}),
            risk_level=risk_level,
            requires_approval=requires_approval,
            reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class ToolResult:
    call_id: str
    name: str
    ok: bool
    content: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class AgentEvent:
    event_id: str
    turn_id: str
    timestamp: str
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, *, turn_id: str, event_type: str, payload: dict[str, Any] | None = None) -> "AgentEvent":
        return cls(
            event_id=f"evt_{uuid4().hex[:12]}",
            turn_id=turn_id,
            timestamp=_utc_now(),
            type=event_type,
            payload=dict(payload or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class ModelResponse:
    assistant_text: str = ""
    reasoning_summary: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_answer: str = ""
    finish_reason: str = "stop"
    raw: Any = None

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(
            {
                "assistant_text": self.assistant_text,
                "reasoning_summary": self.reasoning_summary,
                "tool_calls": [call.to_dict() for call in self.tool_calls],
                "final_answer": self.final_answer,
                "finish_reason": self.finish_reason,
            }
        )


@dataclass
class AgentRunResult:
    ok: bool
    session_id: str
    turn_id: str
    final_answer: str
    events: list[dict[str, Any]]
    summary: dict[str, Any]
    stop_reason: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"
    output_type: AgentOutputType = "answer"

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))
