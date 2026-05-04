"""Retry/replan helpers for AgentLoop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import ToolCall, ToolResult


@dataclass
class ErrorClassification:
    category: str
    retryable: bool
    replan: bool
    reason: str


class ErrorClassifier:
    def classify(self, tool_result: ToolResult) -> ErrorClassification:
        err = str(tool_result.error or "").lower()
        if not err:
            return ErrorClassification(category="none", retryable=False, replan=False, reason="no_error")
        if "timeout" in err:
            return ErrorClassification(category="timeout", retryable=True, replan=False, reason="command_timeout")
        if "approval_required" in err:
            return ErrorClassification(category="approval", retryable=False, replan=True, reason="approval_required")
        if "unknown tool" in err or "unknown_tool" in err:
            return ErrorClassification(category="tool_schema", retryable=True, replan=True, reason="schema_mismatch")
        if "not found" in err:
            return ErrorClassification(category="not_found", retryable=False, replan=True, reason="missing_target")
        if "assertion" in err or "failed" in err:
            return ErrorClassification(category="test_failed", retryable=False, replan=True, reason="tests_failed")
        return ErrorClassification(category="other", retryable=False, replan=True, reason="tool_failed")


class RetryPolicy:
    def __init__(self, *, max_retries: int = 2) -> None:
        self.max_retries = max_retries
        self.retry_counts: dict[str, int] = {}

    def should_retry(self, call: ToolCall, classification: ErrorClassification) -> bool:
        if not classification.retryable:
            return False
        key = f"{call.name}:{classification.category}"
        used = self.retry_counts.get(key, 0)
        if used >= self.max_retries:
            return False
        self.retry_counts[key] = used + 1
        return True


class ReplanPolicy:
    def __init__(self, *, max_replans: int = 2) -> None:
        self.max_replans = max_replans
        self.replan_count = 0

    def should_replan(self, classification: ErrorClassification) -> bool:
        if not classification.replan:
            return False
        if self.replan_count >= self.max_replans:
            return False
        self.replan_count += 1
        return True

    def build_replan_observation(self, tool_result: ToolResult, classification: ErrorClassification) -> dict[str, Any]:
        return {
            "event": "replan_hint",
            "tool_name": tool_result.name,
            "category": classification.category,
            "reason": classification.reason,
            "error": tool_result.error,
        }

