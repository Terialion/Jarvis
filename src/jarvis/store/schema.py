"""Schema records for durable ThreadStore persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ThreadRecord:
    thread_id: str
    title: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TurnRecord:
    turn_id: str
    thread_id: str
    input_redacted: str
    output_summary_redacted: str
    output_type: str
    stop_reason: str | None = None
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MessageRecord:
    message_id: str
    thread_id: str
    turn_id: str | None
    role: str
    content_redacted: str
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCallRecord:
    call_id: str
    thread_id: str
    turn_id: str
    tool_name: str
    args_redacted: dict[str, Any] | str
    result_redacted: dict[str, Any] | str | None
    status: str
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SkillObservationRecord:
    observation_id: str
    thread_id: str
    turn_id: str | None
    skill_name: str
    summary_redacted: str
    related_files: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchObservationRecord:
    observation_id: str
    thread_id: str
    turn_id: str | None
    query_redacted: str
    sources_redacted: list[dict[str, Any]] = field(default_factory=list)
    evidence_redacted: list[dict[str, Any]] = field(default_factory=list)
    answer_summary_redacted: str = ""
    confidence: float = 0.0
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalAuditRecord:
    approval_id: str
    thread_id: str | None
    turn_id: str | None
    tool_name: str
    arguments_preview_redacted: dict[str, Any] | str
    status: str
    decision: str | None = None
    reason_redacted: str | None = None
    created_at: str = field(default_factory=utc_now)
    decided_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActiveTaskStateRecord:
    thread_id: str
    summary_redacted: str
    related_files: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HandoffSummaryRecord:
    thread_id: str
    summary_redacted: str
    risks: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectFactsRecord:
    project_id: str
    facts_redacted: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UserMemoryRecord:
    key: str
    value_redacted: str
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectMemoryRecord:
    project_id: str
    key: str
    value_redacted: str
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
