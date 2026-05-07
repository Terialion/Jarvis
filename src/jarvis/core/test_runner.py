"""Test Runner module for Jarvis Core Phase 1."""

from __future__ import annotations

import subprocess
from pathlib import Path
from time import perf_counter

from .result import error_result, ok_result


class TestRunner:
    """Execute test commands and return normalized test outcomes."""
    __test__ = False

    def __init__(
        self,
        test_commands: list[str] | None = None,
        fallback_on_assertion: bool = False,
        fallback_on_env_error: bool = True,
        fallback_attempt_limit: int = 3,
    ) -> None:
        self.test_commands = [cmd for cmd in (test_commands or []) if str(cmd).strip()]
        self._config_warnings: list[dict] = []
        self.fallback_on_assertion = self._coerce_bool(
            "fallback_on_assertion",
            fallback_on_assertion,
            False,
            self._config_warnings,
        )
        self.fallback_on_env_error = self._coerce_bool(
            "fallback_on_env_error",
            fallback_on_env_error,
            True,
            self._config_warnings,
        )
        self.fallback_attempt_limit = self._coerce_attempt_limit(
            fallback_attempt_limit,
            3,
            self._config_warnings,
        )

    @classmethod
    def from_rules(cls, rules: dict | None) -> "TestRunner":
        rules = rules or {}
        return cls(
            test_commands=list(rules.get("test_commands") or []),
            fallback_on_assertion=rules.get("fallback_on_assertion", False),
            fallback_on_env_error=rules.get("fallback_on_env_error", True),
            fallback_attempt_limit=rules.get("fallback_attempt_limit", 3),
        )

    def apply_rules(self, rules: dict) -> None:
        commands = [cmd for cmd in list(rules.get("test_commands") or []) if str(cmd).strip()]
        if commands:
            self.test_commands = commands
        self.fallback_on_assertion = self._coerce_bool(
            "fallback_on_assertion",
            rules.get("fallback_on_assertion", self.fallback_on_assertion),
            self.fallback_on_assertion,
            self._config_warnings,
        )
        self.fallback_on_env_error = self._coerce_bool(
            "fallback_on_env_error",
            rules.get("fallback_on_env_error", self.fallback_on_env_error),
            self.fallback_on_env_error,
            self._config_warnings,
        )
        self.fallback_attempt_limit = self._coerce_attempt_limit(
            rules.get("fallback_attempt_limit", self.fallback_attempt_limit),
            self.fallback_attempt_limit,
            self._config_warnings,
        )

    def run_test(self, command: str | None, cwd: str, timeout_s: int = 60) -> dict:
        started = perf_counter()
        working_dir = Path(cwd)
        if not working_dir.exists() or not working_dir.is_dir():
            return error_result(
                "CMD_INVALID_CWD",
                f"Invalid cwd: {cwd}",
                {"cwd": cwd},
                started,
            )
        if timeout_s <= 0:
            return error_result(
                "COMMON_INVALID_INPUT",
                "timeout_s must be > 0",
                {"timeout_s": timeout_s},
                started,
            )
        explicit_command = (command or "").strip()
        candidates = [explicit_command] if explicit_command else list(self.test_commands)
        if not candidates:
            return error_result(
                "COMMON_INVALID_INPUT",
                "No test command provided and no default test_commands configured",
                {"command": command, "test_commands": self.test_commands},
                started,
            )

        effective_limit = self._effective_attempt_limit(len(candidates))
        attempt_limit_reason = self._attempt_limit_reason(len(candidates), effective_limit)
        limited_candidates = candidates[:effective_limit]
        attempted_commands: list[str] = []
        last_data: dict | None = None
        for idx, candidate in enumerate(limited_candidates):
            attempted_commands.append(candidate)
            try:
                completed = subprocess.run(
                    candidate,
                    cwd=str(working_dir),
                    timeout=timeout_s,
                    shell=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                passed = completed.returncode == 0
                summary = None if passed else self._extract_failure_summary(completed.stdout, completed.stderr)
                last_data = {
                    "passed": passed,
                    "failure_summary": summary,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "command": candidate,
                    "exit_code": completed.returncode,
                }
                if passed:
                    return ok_result(
                        {
                            **last_data,
                            "attempted_commands": attempted_commands,
                            "attempted_count": len(attempted_commands),
                            "selected_command": candidate,
                            "fallback_used": idx > 0,
                            "attempt_limit_used": effective_limit,
                            "attempt_limit_reason": attempt_limit_reason,
                            "fallback_policy": self._fallback_policy_report(),
                            "duration_ms": max(0, int((perf_counter() - started) * 1000)),
                        },
                        started,
                    )
                if not summary:
                    return error_result(
                        "TEST_NO_SUMMARY",
                        "Unable to extract failure summary",
                        {
                            "command": command,
                            "selected_command": candidate,
                            "attempted_commands": attempted_commands,
                            "cwd": str(working_dir),
                            "exit_code": completed.returncode,
                        },
                        started,
                    )
                if not self._should_try_fallback(
                    failure_summary=summary,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                    has_next=(idx < len(limited_candidates) - 1),
                    fallback_on_assertion=self.fallback_on_assertion,
                    fallback_on_env_error=self.fallback_on_env_error,
                ):
                    return ok_result(
                        {
                            **last_data,
                            "attempted_commands": attempted_commands,
                            "attempted_count": len(attempted_commands),
                            "selected_command": candidate,
                            "fallback_used": idx > 0,
                            "attempt_limit_used": effective_limit,
                            "attempt_limit_reason": attempt_limit_reason,
                            "fallback_policy": self._fallback_policy_report(),
                            "duration_ms": max(0, int((perf_counter() - started) * 1000)),
                        },
                        started,
                    )
            except subprocess.TimeoutExpired as exc:
                return error_result(
                    "TEST_TIMEOUT",
                    "Test execution timed out",
                    {
                        "command": command,
                        "selected_command": candidate,
                        "attempted_commands": attempted_commands,
                        "attempted_count": len(attempted_commands),
                        "cwd": str(working_dir),
                        "timeout_s": timeout_s,
                        "stdout": exc.stdout,
                        "stderr": exc.stderr,
                    },
                    started,
                )
            except Exception as exc:  # pragma: no cover - defensive
                if idx < len(limited_candidates) - 1:
                    continue
                return error_result(
                    "TEST_EXEC_FAILED",
                    "Test execution failed unexpectedly",
                    {
                        "command": command,
                        "selected_command": candidate,
                        "attempted_commands": attempted_commands,
                        "exception": str(exc),
                    },
                    started,
                )

        # All candidates exhausted.
        return ok_result(
            {
                "passed": False,
                "failure_summary": (last_data or {}).get("failure_summary") or "All test command candidates failed",
                "stdout": (last_data or {}).get("stdout", ""),
                "stderr": (last_data or {}).get("stderr", ""),
                "command": (last_data or {}).get("command", candidates[-1]),
                "exit_code": (last_data or {}).get("exit_code", 1),
                "attempted_commands": attempted_commands,
                "attempted_count": len(attempted_commands),
                "selected_command": (last_data or {}).get("command", candidates[-1]),
                "fallback_used": len(attempted_commands) > 1,
                "attempt_limit_used": effective_limit,
                "attempt_limit_reason": attempt_limit_reason,
                "fallback_policy": self._fallback_policy_report(),
                "duration_ms": max(0, int((perf_counter() - started) * 1000)),
            },
            started,
        )

    @staticmethod
    def _extract_failure_summary(stdout: str, stderr: str) -> str | None:
        text = "\n".join([stdout or "", stderr or ""]).strip()
        if not text:
            return None
        prioritized_markers = [
            "AssertionError",
            "ModuleNotFoundError",
            "ImportError",
            "No module named",
            "SyntaxError",
            "NameError",
            "TypeError",
            "ValueError",
            "RuntimeError",
            "FAILED",
            "ERROR",
        ]
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for marker in prioritized_markers:
            for line in lines:
                if marker in line:
                    return line[:300]
        return lines[-1][:300] if lines else None

    @staticmethod
    def _should_try_fallback(
        failure_summary: str,
        stdout: str,
        stderr: str,
        has_next: bool,
        fallback_on_assertion: bool,
        fallback_on_env_error: bool,
    ) -> bool:
        if not has_next:
            return False
        merged = "\n".join([failure_summary or "", stdout or "", stderr or ""]).lower()
        infra_markers = [
            "not recognized as an internal or external command",
            "command not found",
            "can't open file",
            "no module named",
            "modulenotfounderror",
            "importerror",
            "is not recognized",
        ]
        if fallback_on_env_error and any(marker in merged for marker in infra_markers):
            return True
        # Assertion-style failures indicate a valid test command, so do not fallback.
        if "assertionerror" in merged or "assert " in merged:
            return fallback_on_assertion
        return False

    def _fallback_policy_report(self) -> dict:
        return {
            "fallback_on_assertion": self.fallback_on_assertion,
            "fallback_on_env_error": self.fallback_on_env_error,
            "fallback_attempt_limit": self.fallback_attempt_limit,
            "warnings": list(self._config_warnings),
        }

    @staticmethod
    def _coerce_bool(name: str, value: object, default: bool, warnings: list[dict]) -> bool:
        if isinstance(value, bool):
            return value
        warnings.append(
            {
                "category": "fallback_config",
                "code": "FALLBACK_BOOL_INVALID_TYPE",
                "message": f"{name} invalid type {type(value).__name__}, fallback to {default}",
                "details": {"name": name, "default": default},
            }
        )
        return default

    @staticmethod
    def _coerce_attempt_limit(value: object, default: int, warnings: list[dict]) -> int:
        if isinstance(value, int) and value > 0:
            return value
        warnings.append(
            {
                "category": "fallback_config",
                "code": "FALLBACK_ATTEMPT_LIMIT_INVALID",
                "message": f"fallback_attempt_limit invalid, fallback to {default}",
                "details": {"received": value, "default": default},
            }
        )
        return default

    def _effective_attempt_limit(self, candidate_count: int) -> int:
        if candidate_count <= 0:
            return 0
        return min(max(1, self.fallback_attempt_limit), candidate_count)

    def _attempt_limit_reason(self, candidate_count: int, effective_limit: int) -> str:
        if candidate_count <= 0:
            return "no_candidates"
        if any(w.get("code") == "FALLBACK_ATTEMPT_LIMIT_INVALID" for w in self._config_warnings):
            return "invalid_limit_fallback_default"
        if self.fallback_attempt_limit > candidate_count:
            return "clamped_to_candidate_count"
        if self.fallback_attempt_limit == candidate_count:
            return "limit_matches_candidate_count"
        return "limit_applied"
