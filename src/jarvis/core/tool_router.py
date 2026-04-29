"""Tool Router module for Jarvis Core Phase 1."""

from __future__ import annotations

from time import perf_counter

from .result import error_result, ok_result


class ToolRouter:
    """Rule-first router for fixed loop decisions in Phase 1."""

    _allowed_actions = {
        "repo_read",
        "file_edit",
        "run_command",
        "run_test",
        "analyze_failure",
        "stop_and_ask_user",
    }

    def choose_next_action(self, task_context: dict) -> dict:
        started = perf_counter()
        if not isinstance(task_context, dict):
            return error_result(
                "COMMON_INVALID_INPUT",
                "task_context must be a dict",
                {"received_type": str(type(task_context))},
                started,
            )

        risk = bool(task_context.get("high_risk_write") or task_context.get("needs_confirmation"))
        tests_failed = bool(task_context.get("tests_failed"))
        failure_known = bool(task_context.get("failure_analyzed"))
        repo_scanned = bool(task_context.get("repo_scanned"))
        file_edited = bool(task_context.get("file_edited"))
        run_command_first = bool(task_context.get("run_command_first"))

        if risk:
            return self._ok(
                action_type="stop_and_ask_user",
                tool_name="human_handoff",
                reason="High-risk action requires explicit user confirmation.",
                confidence=0.98,
                started=started,
            )

        if tests_failed and not failure_known:
            return self._ok(
                action_type="analyze_failure",
                tool_name="failure_analyzer.analyze",
                reason="Tests failed and no failure classification is available.",
                confidence=0.94,
                started=started,
            )

        if tests_failed and failure_known:
            return self._ok(
                action_type="run_test",
                tool_name="test_runner.run_test",
                reason="Failure was analyzed; rerun tests after targeted adjustment.",
                confidence=0.82,
                started=started,
            )

        if not repo_scanned:
            return self._ok(
                action_type="repo_read",
                tool_name="repo_reader.search_symbol",
                reason="Need repository context before edits.",
                confidence=0.9,
                started=started,
            )

        if repo_scanned and not file_edited:
            return self._ok(
                action_type="file_edit",
                tool_name="file_editor.replace_text",
                reason="Relevant location found; apply minimal patch.",
                confidence=0.88,
                started=started,
            )

        if run_command_first:
            return self._ok(
                action_type="run_command",
                tool_name="command_runner.run",
                reason="Task policy requests command execution before tests.",
                confidence=0.75,
                started=started,
            )

        return self._ok(
            action_type="run_test",
            tool_name="test_runner.run_test",
            reason="Patch appears applied; validate by running tests.",
            confidence=0.86,
            started=started,
        )

    def _ok(self, action_type: str, tool_name: str, reason: str, confidence: float, started: float) -> dict:
        if action_type not in self._allowed_actions:
            return error_result(
                "ROUTER_NO_ACTION",
                "Router selected unsupported action type",
                {"action_type": action_type},
                started,
            )
        return ok_result(
            {
                "action_type": action_type,
                "tool_name": tool_name,
                "reason": reason,
                "confidence": round(confidence, 2),
            },
            started,
        )

