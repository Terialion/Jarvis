"""Failure Analyzer module for Jarvis Core Phase 1."""

from __future__ import annotations

from time import perf_counter

from .result import error_result, ok_result


class FailureAnalyzer:
    """Classify test failures and suggest a single next step."""

    def analyze(self, test_run: dict, task_context: dict) -> dict:
        started = perf_counter()
        if not isinstance(test_run, dict):
            return error_result(
                "COMMON_INVALID_INPUT",
                "test_run must be a dict",
                {"received_type": str(type(test_run))},
                started,
            )
        if not isinstance(task_context, dict):
            return error_result(
                "COMMON_INVALID_INPUT",
                "task_context must be a dict",
                {"received_type": str(type(task_context))},
                started,
            )

        data = test_run.get("data", test_run)
        stdout = str(data.get("stdout") or "")
        stderr = str(data.get("stderr") or "")
        failure_summary = str(data.get("failure_summary") or "")
        merged = "\n".join([failure_summary, stdout, stderr]).lower()
        exit_code = data.get("exit_code")

        failure_type, summary, next_action, needs_human = self._classify(merged, failure_summary, exit_code)
        if failure_type == "unknown":
            return error_result(
                "ANALYZER_UNKNOWN_FAILURE",
                "Unable to classify failure with confidence",
                {
                    "failure_type": failure_type,
                    "summary": summary,
                    "suggested_next_action": next_action,
                    "needs_human_confirmation": needs_human,
                },
                started,
            )
        return ok_result(
            {
                "failure_type": failure_type,
                "summary": summary,
                "suggested_next_action": next_action,
                "needs_human_confirmation": needs_human,
            },
            started,
        )

    def _classify(self, merged: str, failure_summary: str, exit_code: int | None) -> tuple[str, str, str, bool]:
        if "assertionerror" in merged or "assert " in merged:
            return (
                "code_bug",
                failure_summary or "Assertion failed; likely code behavior mismatch.",
                "inspect_code_and_patch_minimally",
                False,
            )

        if any(
            marker in merged
            for marker in ["module not found", "no module named", "config", "environment variable", "keyerror"]
        ):
            return (
                "config_issue",
                failure_summary or "Configuration or dependency issue detected.",
                "check_project_config_and_dependencies",
                True,
            )

        if any(marker in merged for marker in ["syntaxerror", "malformed", "invalid syntax", "test collection failed"]):
            return (
                "test_issue",
                failure_summary or "Test artifact appears malformed or invalid.",
                "fix_test_definition_before_code_patch",
                False,
            )

        if exit_code is None or any(
            marker in merged for marker in ["segmentation fault", "fatal", "crashed", "internal error", "traceback"]
        ):
            return (
                "infra_like_issue",
                failure_summary or "Runtime/runner instability detected.",
                "retry_or_stabilize_runner_environment",
                True,
            )

        return ("unknown", failure_summary or "Unclassified failure.", "ask_human_for_next_step", True)

