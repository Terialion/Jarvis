"""Core types for Jarvis AgentLoop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Literal
from uuid import uuid4

MessageRole = Literal["system", "user", "assistant", "tool"]
AgentOutputType = Literal["answer", "tool_result", "clarification", "refusal", "partial", "error"]

_SENSITIVE_KEYWORDS = ("token", "secret", "api_key", "password", "authorization", "private_key")
_SECRET_TEXT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{4,}\b"), "[REDACTED_SECRET]"),
    (
        re.compile(r"(?i)\b(JARVIS_LLM_API_KEY|DEEPSEEK_API_KEY|OPENAI_API_KEY)\s*=\s*\S+"),
        lambda m: f"{m.group(1)}:[REDACTED]",
    ),
    (
        re.compile(r"(?i)\b(api[_-]?key|token|password)\s*[:=]\s*\S+"),
        lambda m: f"{m.group(1)}:[REDACTED]",
    ),
    (
        re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+"),
        "Authorization:[REDACTED]",
    ),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_secret_text(text: str) -> str:
    masked = str(text or "")
    for pattern, replacement in _SECRET_TEXT_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


def contains_secret_text(text: str) -> bool:
    raw = str(text or "")
    return redact_secret_text(raw) != raw


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
    if isinstance(value, str):
        return redact_secret_text(value)
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
class ProjectContext:
    cwd: str
    repo_root: str | None = None
    project_name: str | None = None
    project_files_hint: list[str] = field(default_factory=list)
    project_instructions: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class ConversationContext:
    thread_id: str | None = None
    turn_id: str = ""
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    compacted_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class MemoryContext:
    short_term: dict[str, Any] = field(default_factory=dict)
    long_term_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class SkillSpecRecord:
    name: str
    description: str
    path: str
    risk_level: str
    allowed_tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    body_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class SkillContext:
    available_skills: list[dict[str, Any]] = field(default_factory=list)
    loaded_skills: list[str] = field(default_factory=list)
    loaded_skill_bodies: dict[str, str] = field(default_factory=dict)
    implicit_skill_invocations: list[str] = field(default_factory=list)
    skill_observations: list[dict[str, Any]] = field(default_factory=list)
    research_observations: list[dict[str, Any]] = field(default_factory=list)
    active_task: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class ContextPack:
    project: ProjectContext
    conversation: ConversationContext
    memory: MemoryContext
    skills: SkillContext
    token_budget: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))


@dataclass
class TurnContext:
    user_input: str
    cwd: str
    model_provider: str | None = None
    model_name: str | None = None
    permission_mode: str = "workspace_write"
    context_pack: ContextPack | None = None
    model_backend: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    timestamp_utc: str = field(default_factory=_utc_now)

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
        id: str | None = None,
        risk_level: str = "low",
        requires_approval: bool = False,
        reason: str | None = None,
    ) -> "ToolCall":
        return cls(
            id=id or f"call_{uuid4().hex[:12]}",
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
    duration_s: float | None = None

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
class ModelChunk:
    """A single chunk from a streaming model response."""

    kind: str = ""  # "text_delta" | "tool_call_delta" | "done" | "reasoning_delta" | "progress_delta"
    text_delta: str = ""
    progress_delta: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    tool_arguments_delta: str = ""
    finish_reason: str = ""
    reasoning_delta: str = ""
    usage: dict | None = None  # Provider token usage info when available
    file_change: dict | None = None  # {path, diff_text, added, removed, status}

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
    session_id: str = ""
    turn_id: str = ""
    final_answer: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    stop_reason: str = "completed"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"
    output_type: AgentOutputType = "answer"
    available_skills: list[str] = field(default_factory=list)
    loaded_skills: list[str] = field(default_factory=list)
    skill_loads_count: int = 0
    skills_used: list[str] = field(default_factory=list)
    skill_calls_count: int = 0
    skill_results: list[dict[str, Any]] = field(default_factory=list)
    model_backend: str = ""
    model_provider: str = ""
    model_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _redact_value(asdict(self))
