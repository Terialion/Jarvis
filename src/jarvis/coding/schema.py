from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from ..store.redaction import redact_for_persistence


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass
class CodingTask:
    task_id: str
    user_goal: str
    target_files: list[str] = field(default_factory=list)
    mode: Literal["review", "fix", "test", "explain"] = "review"
    status: str = "created"
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def new(cls, *, user_goal: str, mode: Literal["review", "fix", "test", "explain"], target_files: list[str] | None = None) -> "CodingTask":
        return cls(task_id=new_id("codingtask"), user_goal=user_goal, mode=mode, target_files=list(target_files or []))

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(asdict(self)))


@dataclass
class CodeIssue:
    issue_id: str
    file: str | None
    line: int | None
    severity: str
    summary: str
    evidence: list[str] = field(default_factory=list)

    @classmethod
    def new(cls, *, file: str | None, summary: str, severity: str = "medium", line: int | None = None, evidence: list[str] | None = None) -> "CodeIssue":
        return cls(issue_id=new_id("codeissue"), file=file, line=line, severity=severity, summary=summary, evidence=list(evidence or []))

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(asdict(self)))


@dataclass
class PatchPlan:
    plan_id: str
    task_id: str
    summary: str
    target_files: list[str]
    steps: list[str]
    risk_level: str = "medium"
    requires_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(asdict(self)))


@dataclass
class DiffPreview:
    diff_id: str
    task_id: str
    files_changed: list[str]
    unified_diff: str
    risk_level: str = "medium"
    redacted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(asdict(self)))


@dataclass
class PatchApplyResult:
    patch_id: str
    applied: bool
    files_changed: list[str] = field(default_factory=list)
    approval_id: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(asdict(self)))


@dataclass
class TestRunPlan:
    command: str
    reason: str
    expected_signal: str

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(asdict(self)))


@dataclass
class TestRunResult:
    command: str
    passed: bool
    exit_code: int
    stdout_redacted: str = ""
    stderr_redacted: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(asdict(self)))


@dataclass
class FailureAnalysis:
    summary: str
    likely_causes: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(asdict(self)))


@dataclass
class CodingWorkflowResult:
    task_id: str
    status: Literal["completed", "partial", "blocked", "approval_required", "failed"]
    issues: list[CodeIssue] = field(default_factory=list)
    patch_plan: PatchPlan | None = None
    diff_preview: DiffPreview | None = None
    patch_apply_result: PatchApplyResult | None = None
    test_results: list[TestRunResult] = field(default_factory=list)
    failure_analysis: FailureAnalysis | None = None
    summary: str = ""
    remaining_work: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(redact_for_persistence(
            {
                "task_id": self.task_id,
                "status": self.status,
                "issues": [issue.to_dict() for issue in self.issues],
                "patch_plan": self.patch_plan.to_dict() if self.patch_plan else None,
                "diff_preview": self.diff_preview.to_dict() if self.diff_preview else None,
                "patch_apply_result": self.patch_apply_result.to_dict() if self.patch_apply_result else None,
                "test_results": [result.to_dict() for result in self.test_results],
                "failure_analysis": self.failure_analysis.to_dict() if self.failure_analysis else None,
                "summary": self.summary,
                "remaining_work": list(self.remaining_work),
                "events": list(self.events),
                "tool_calls": list(self.tool_calls),
                "tool_results": list(self.tool_results),
            }
        ))
