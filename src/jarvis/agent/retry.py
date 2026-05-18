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
        if "approval_required" in err or "denied" in err or "permission" in err:
            return ErrorClassification(category="permission", retryable=False, replan=True, reason="permission_denied")
        if "unknown tool" in err or "unknown_tool" in err:
            return ErrorClassification(category="tool_schema", retryable=True, replan=True, reason="unknown_tool")
        if "not found" in err or "does_not_exist" in err or "no such file" in err:
            return ErrorClassification(category="not_found", retryable=False, replan=True, reason="missing_target")
        if "invalid" in err or "malformed" in err or "parameter" in err:
            return ErrorClassification(category="bad_params", retryable=True, replan=True, reason="invalid_parameters")
        if "assertion" in err or "test" in err:
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


@dataclass
class FailureRecord:
    tool_name: str
    error_category: str
    error_message: str
    step: int


class FailureTracker:
    """Track failures and repetition to detect infinite loops."""

    def __init__(self, *, max_consecutive: int = 5, max_same_tool: int = 4, max_repeat: int = 3) -> None:
        self.max_consecutive = max_consecutive
        self.max_same_tool = max_same_tool
        self.max_repeat = max_repeat
        self.consecutive_failures: list[FailureRecord] = []
        self.tool_failure_counts: dict[str, int] = {}
        self.tool_total_calls: dict[str, int] = {}
        self._synthesis_nudged: set[str] = set()

    def record_failure(self, tool_name: str, error_category: str, error_message: str, step: int) -> None:
        self.consecutive_failures.append(
            FailureRecord(tool_name=tool_name, error_category=error_category,
                          error_message=error_message, step=step)
        )
        self.tool_failure_counts[tool_name] = self.tool_failure_counts.get(tool_name, 0) + 1
        self.tool_total_calls[tool_name] = self.tool_total_calls.get(tool_name, 0) + 1

    def record_success(self, tool_name: str) -> None:
        self.consecutive_failures.clear()
        self.tool_failure_counts.pop(tool_name, None)
        self.tool_total_calls[tool_name] = self.tool_total_calls.get(tool_name, 0) + 1

    def should_stop(self) -> tuple[bool, str]:
        """Check if we should stop due to consecutive failures. Returns (stop, reason)."""
        if len(self.consecutive_failures) >= self.max_consecutive:
            last = self.consecutive_failures[-1]
            return True, (
                f"{self.max_consecutive} consecutive tool failures. "
                f"Last error ({last.tool_name}): {last.error_message[:200]}"
            )
        return False, ""

    def should_reject_tool(self, tool_name: str) -> tuple[bool, str, str]:
        """Returns (reject, reason, kind) where kind is 'failure' (too many errors)
        or 'repeat' (too many total calls — model should synthesize instead)."""
        fail_count = self.tool_failure_counts.get(tool_name, 0)
        if fail_count >= self.max_same_tool:
            return True, (
                f"Tool `{tool_name}` has failed {fail_count} times; try a different approach or stop."
            ), "failure"
        total = self.tool_total_calls.get(tool_name, 0)
        if total >= self.max_repeat:
            return True, (
                f"Tool `{tool_name}` has been called {total} times this turn. "
                "Stop calling it and synthesize a final answer from the results you already have."
            ), "repeat"
        return False, "", ""

    def is_repeat_hard_stop(self, tool_name: str) -> bool:
        """Returns True if this tool already received a synthesis nudge and
        the model is still trying to call it — hard stop is warranted."""
        if tool_name in self._synthesis_nudged:
            return True
        self._synthesis_nudged.add(tool_name)
        return False


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

