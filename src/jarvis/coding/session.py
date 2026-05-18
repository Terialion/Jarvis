"""CodingSession: outer iterative loop (plan → execute → validate → rethink → deliver).

Wraps AgentLoop to provide the write → run → fix → repeat cycle that
Claude Code / Codex / OpenClaw implement for autonomous coding tasks.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..agent.loop import AgentLoop
from ..agent.model import RuntimeModelClient
from ..agent.types import AgentRunResult, ChatInput


@dataclass
class ValidationResult:
    tests_passed: bool = False
    lint_ok: bool = True  # True if no linter available
    test_output: str = ""
    lint_output: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class AttemptRecord:
    attempt: int
    plan: str = ""
    result: AgentRunResult | None = None
    validation: ValidationResult | None = None
    revised_plan: str = ""


def _find_test_files(changed_py_files: list[str], workspace_root: str) -> list[str]:
    """Map changed source files to likely test files."""
    root = Path(workspace_root)
    test_files: list[str] = []
    for f in changed_py_files:
        p = Path(f)
        stem = p.stem
        # Strip common prefixes to match test files
        bare_stems = {stem}
        if stem.startswith("buggy_"):
            bare_stems.add(stem.replace("buggy_", "", 1))
        for prefix in ("test_", "spec_", "tests_"):
            if stem.startswith(prefix):
                bare_stems.add(stem[len(prefix):])

        candidates = []
        for s in bare_stems:
            candidates.extend([
                p.parent / f"test_{s}.py",
                p.parent / f"{s}_test.py",
                root / "tests" / f"test_{s}.py",
                root / "test" / f"test_{s}.py",
            ])
        # Also check for ANY test_*.py in the same directory
        if p.parent.exists():
            for existing in p.parent.glob("test_*.py"):
                if str(existing) not in test_files:
                    test_files.append(str(existing))
        for c in candidates:
            if c.exists() and str(c) not in test_files:
                test_files.append(str(c))
    return test_files


def validate_changes(
    changed_files: list[str], workspace_root: str, *, run_lint: bool = True
) -> ValidationResult:
    """Run pytest on related tests and ruff on changed Python files."""
    errors: list[str] = []
    test_output = ""
    lint_output = ""
    tests_passed = True
    lint_ok = True

    py_files = [f for f in changed_files if f.endswith(".py")]
    if not py_files:
        return ValidationResult(tests_passed=True, lint_ok=True)

    # 1. Run pytest on scoped test files
    test_files = _find_test_files(py_files, workspace_root)
    if test_files:
        try:
            proc = subprocess.run(
                ["python", "-m", "pytest", "-q"] + test_files,
                cwd=workspace_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            test_output = proc.stdout + "\n" + proc.stderr
            if proc.returncode != 0:
                tests_passed = False
                errors.append(f"Tests failed (exit={proc.returncode})")
        except FileNotFoundError:
            test_output = "pytest not installed"
            errors.append("pytest not found")
            tests_passed = False
        except subprocess.TimeoutExpired:
            test_output = "pytest timed out"
            errors.append("pytest timed out")
            tests_passed = False
    else:
        test_output = "(no test files found for changed sources)"

    # 2. Run ruff on changed Python files (if available)
    if run_lint and py_files:
        try:
            proc = subprocess.run(
                ["ruff", "check"] + py_files,
                cwd=workspace_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            lint_output = proc.stdout + "\n" + proc.stderr
            if proc.returncode != 0:
                lint_ok = False
                errors.append(f"Lint failed (exit={proc.returncode})")
        except FileNotFoundError:
            lint_output = "(ruff not installed)"
        except subprocess.TimeoutExpired:
            lint_output = "(ruff timed out)"

    return ValidationResult(
        tests_passed=tests_passed,
        lint_ok=lint_ok,
        test_output=test_output.strip(),
        lint_output=lint_output.strip(),
        errors=errors,
    )


def _extract_errors(validation: ValidationResult) -> str:
    """Extract a concise error summary from validation output."""
    parts: list[str] = []
    if not validation.tests_passed and validation.test_output:
        # Get the last 40 lines of test output (where failures are)
        lines = validation.test_output.splitlines()
        relevant = lines[-40:] if len(lines) > 40 else lines
        parts.append("=== Test failures ===\n" + "\n".join(relevant))
    if not validation.lint_ok and validation.lint_output:
        parts.append("=== Lint errors ===\n" + validation.lint_output[:2000])
    return "\n".join(parts)


def _detect_changed_files(result: AgentRunResult, workspace_root: str) -> list[str]:
    """Detect which files were modified by the agent's tool calls."""
    changed: set[str] = set()
    for tc in result.tool_calls or []:
        name = tc.get("name", tc.get("tool_name", ""))
        args = tc.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                continue
        if not isinstance(args, dict):
            continue
        if name in ("file_editor.write_file", "file_editor.replace_text",
                     "file_editor.insert_text", "patch.apply"):
            path = str(args.get("path", args.get("file_path", "")))
            if path:
                abs_path = Path(workspace_root) / path if not Path(path).is_absolute() else Path(path)
                if abs_path.exists():
                    changed.add(str(abs_path))
    return list(changed)


class CodingSession:
    """Outer iterative loop for autonomous coding tasks.

    Wraps AgentLoop with: plan → execute → validate → (rethink → execute)* → deliver.
    """

    def __init__(
        self,
        *,
        project_root: str = ".",
        max_attempts: int = 3,
        timeout_s: int = 300,
        permission_mode: str = "workspace_write",
        auto_approve: bool = False,
    ) -> None:
        self.project_root = str(Path(project_root).resolve())
        self.max_attempts = max_attempts
        self.timeout_s = timeout_s
        self.permission_mode = permission_mode
        self.auto_approve = auto_approve

    def run(self, user_goal: str) -> dict[str, Any]:
        """Execute the coding session: plan → iterate → validate → deliver.

        Returns a dict with: ok, final_answer, attempts, changed_files,
        validation, stop_reason.
        """
        attempts: list[AttemptRecord] = []
        final_result: AgentRunResult | None = None
        final_answer = ""
        stop_reason = "max_attempts"
        success = False

        for attempt_num in range(1, self.max_attempts + 1):
            record = AttemptRecord(attempt=attempt_num)

            # Build the prompt for this attempt
            if attempt_num == 1:
                prompt = self._build_initial_prompt(user_goal)
            else:
                prompt = self._build_rethink_prompt(user_goal, attempts)

            record.plan = prompt

            # Execute via AgentLoop
            loop = self._create_loop()
            chat_input = ChatInput(
                text=prompt,
                cwd=self.project_root,
                metadata={"source": "coding_session", "attempt": attempt_num},
            )
            result = loop.run_turn(chat_input)
            record.result = result
            final_result = result
            final_answer = result.final_answer

            # Detect changed files and validate
            changed_files = _detect_changed_files(result, self.project_root)
            validation = validate_changes(changed_files, self.project_root)
            record.validation = validation

            attempts.append(record)

            if validation.tests_passed and validation.lint_ok:
                stop_reason = "success"
                success = True
                break

            # Rethink: extract errors for the next attempt
            error_summary = _extract_errors(validation)
            if not error_summary and not changed_files:
                error_summary = "No file changes were made. Please produce code changes."
            elif not error_summary and not validation.tests_passed:
                error_summary = "Tests did not pass but no test output was captured."

            record.revised_plan = error_summary

        return {
            "ok": success,
            "final_answer": final_answer,
            "attempts": attempts,
            "changed_files": _detect_changed_files(final_result, self.project_root) if final_result else [],
            "stop_reason": stop_reason,
            "total_attempts": len(attempts),
        }

    def _create_loop(self) -> AgentLoop:
        """Create a fresh AgentLoop for each attempt."""
        return AgentLoop(
            project_root=self.project_root,
            max_steps=20,
            timeout_s=self.timeout_s,
            permission_mode=self.permission_mode,
            auto_approve=self.auto_approve,
        )

    def _build_initial_prompt(self, user_goal: str) -> str:
        """Build the initial coding prompt."""
        return (
            "You are an autonomous coding agent. Your task is to write code that works.\n\n"
            "## Task\n"
            f"{user_goal}\n\n"
            "## Instructions\n"
            "1. First, explore the relevant files to understand the codebase.\n"
            "2. Write the code changes needed to complete the task.\n"
            "3. Run the tests to verify your changes work.\n"
            "4. If tests fail, analyze the error and fix the code.\n"
            "5. When all tests pass, provide a summary of what you changed.\n\n"
            "Important: Always run tests after making code changes. "
            "If you change a file, run the related tests to confirm correctness."
        )

    def _build_rethink_prompt(
        self, user_goal: str, attempts: list[AttemptRecord]
    ) -> str:
        """Build a rethink prompt incorporating previous failures."""
        last = attempts[-1] if attempts else None
        if not last or not last.validation:
            return self._build_initial_prompt(user_goal)

        error_text = _extract_errors(last.validation) if last.validation else ""
        prev_answer = ""
        if last.result and last.result.final_answer:
            prev_answer = last.result.final_answer[:2000]

        return (
            "You are an autonomous coding agent. Your previous attempt had issues.\n\n"
            "## Original Task\n"
            f"{user_goal}\n\n"
            "## Previous Attempt Result\n"
            f"{prev_answer}\n\n"
            "## Errors from Previous Attempt\n"
            f"{error_text}\n\n"
            "## Instructions\n"
            "1. Read the files that had errors to understand the current state.\n"
            "2. Analyze what went wrong in the previous attempt.\n"
            "3. Write a DIFFERENT fix — do not repeat the same approach.\n"
            "4. Run the tests to verify your fix works.\n"
            "5. If you cannot fix the issue, explain what's blocking you.\n\n"
            "Important: Your previous approach FAILED. Try a different strategy."
        )
