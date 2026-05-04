"""Core data contracts for the chat-first Jarvis agent loop.

These are intentionally small and Python-native. They should wrap existing
Jarvis TaskRuntime/Replay/SkillHarness objects rather than replace them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

Role = Literal["system", "user", "assistant", "tool"]


class TurnStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ChatInput:
    text: str
    thread_id: str | None = None
    project_root: str | None = None
    user_id: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatMessage:
    role: Role
    content: str
    message_id: str = field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "low"
    source: str = "jarvis"
    requires_approval: bool = False


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = field(default_factory=lambda: f"call_{uuid4().hex[:12]}")
    source: str = "model"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    call_id: str
    name: str
    ok: bool
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_type: str | None = None
    duration_ms: int = 0


@dataclass
class ModelResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "stop"
    raw: Any = None


@dataclass
class AgentEvent:
    type: str
    turn_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")


@dataclass
class AgentRunResult:
    thread_id: str
    turn_id: str
    status: TurnStatus
    answer: str
    messages: list[ChatMessage] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    stop_reason: str = "stop"
