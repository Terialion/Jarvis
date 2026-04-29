"""Command Runner module for Jarvis Core Phase 1."""

from __future__ import annotations

import subprocess
from pathlib import Path
from time import perf_counter
from typing import Callable

from .result import error_result, ok_result
from .safety_guard import SafetyGuard


CommandValidator = Callable[[str, str], bool]


class CommandRunner:
    """Run shell commands with safety hook points and uniform errors."""

    def __init__(
        self,
        command_validator: CommandValidator | None = None,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        self.command_validator = command_validator
        self.safety_guard = safety_guard

    def run(self, command: str, cwd: str, timeout_s: int = 30, env: dict | None = None) -> dict:
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
        if self.safety_guard is not None:
            guard_result = self.safety_guard.validate_command(command, str(working_dir))
            if not guard_result.get("ok"):
                return error_result(
                    "CMD_BLOCKED_BY_POLICY",
                    "Command validation failed in safety guard",
                    {
                        "command": command,
                        "cwd": str(working_dir),
                        "guard_error": guard_result.get("error"),
                    },
                    started,
                )
            guard_data = guard_result.get("data") or {}
            if not guard_data.get("allowed", False):
                return error_result(
                    "CMD_BLOCKED_BY_POLICY",
                    "Command blocked by safety guard",
                    {
                        "command": command,
                        "cwd": str(working_dir),
                        "reason_code": guard_data.get("reason_code"),
                        "needs_confirmation": bool(guard_data.get("needs_confirmation")),
                    },
                    started,
                )
            if guard_data.get("needs_confirmation"):
                return error_result(
                    "CMD_BLOCKED_BY_POLICY",
                    "Command requires user confirmation before execution",
                    {
                        "command": command,
                        "cwd": str(working_dir),
                        "reason_code": guard_data.get("reason_code"),
                        "needs_confirmation": True,
                    },
                    started,
                )
        if self.command_validator and not self.command_validator(command, str(working_dir)):
            return error_result(
                "CMD_BLOCKED_BY_POLICY",
                "Command blocked by policy hook",
                {"command": command, "cwd": str(working_dir)},
                started,
            )

        try:
            completed = subprocess.run(
                command,
                cwd=str(working_dir),
                timeout=timeout_s,
                env=env,
                shell=True,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                return error_result(
                    "CMD_EXEC_FAILED",
                    "Command exited with non-zero status",
                    {
                        "command": command,
                        "cwd": str(working_dir),
                        "exit_code": completed.returncode,
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                    },
                    started,
                )
            return ok_result(
                {
                    "command": command,
                    "cwd": str(working_dir),
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "timed_out": False,
                    "duration_ms": max(0, int((perf_counter() - started) * 1000)),
                },
                started,
            )
        except subprocess.TimeoutExpired as exc:
            return error_result(
                "CMD_TIMEOUT",
                "Command timed out",
                {
                    "command": command,
                    "cwd": str(working_dir),
                    "timeout_s": timeout_s,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr,
                },
                started,
            )
        except Exception as exc:  # pragma: no cover - defensive
            return error_result(
                "COMMON_INTERNAL_ERROR",
                "Unexpected command runner error",
                {"command": command, "exception": str(exc)},
                started,
            )
