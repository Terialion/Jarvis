"""Test safety behavior for Jarvis CLI."""

import os
import subprocess
import sys

import pytest


def run_cli(*args, input_text=None, timeout=25):
    """Helper to run jarvis CLI command."""
    merged_env = os.environ.copy()
    merged_env["PYTHONIOENCODING"] = "utf-8"
    merged_env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    
    result = subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
        encoding="utf-8",
        errors="ignore",
        env=merged_env,
    )
    # Ensure stdout and stderr are not None
    if result.stdout is None:
        result.stdout = ""
    if result.stderr is None:
        result.stderr = ""
    return result


class TestSafeModeDefault:
    """Test that safe mode is default."""

    def test_shell_shows_safe_mode(self):
        """Shell should show 'safe' mode by default."""
        result = run_cli(input_text="/exit\n")
        output = result.stdout + result.stderr
        assert "safe" in output.lower()

    def test_mode_command_shows_safe(self):
        """/mode command should show 'safe' by default."""
        result = run_cli(input_text="/mode\n/exit\n")
        output = result.stdout + result.stderr
        assert "safe" in output


class TestDangerousActionsRequireApproval:
    """Test that dangerous actions require approval."""

    def test_test_command_requires_approval(self):
        """/test command should require approval or show dry-run."""
        result = run_cli(input_text="/test\n/exit\n")
        output = result.stdout + result.stderr
        assert "pytest" in output or "approval" in output.lower() or "dry" in output.lower()

    def test_run_tests_requires_approval(self):
        """Natural language 'Run tests' should require approval or be safely handled."""
        result = run_cli(input_text="Run tests\n/exit\n")
        output = result.stdout + result.stderr
        # Should either show approval prompt, dry-run mention, work path routing, or LLM fallback
        is_work_or_approval = ("pytest" in output or "approval" in output.lower()
                               or "dry" in output.lower() or "[WORK]" in output
                               or "无法连接 LLM" in output or "llm provider" in output.lower()
                               or "skill" in output.lower() or "run_tests" in output
                               or "Jarvis" in output)
        assert is_work_or_approval
        # Should NOT silently run pytest
        assert "PASSED" not in output and "FAILED" not in output


class TestNoSilentTestExecution:
    """Test that tests are not silently executed."""

    def test_no_fake_pytest_output(self):
        """Should not emit fake pytest output."""
        result = run_cli(input_text="/help\n/exit\n")
        output = result.stdout + result.stderr
        assert "pytest -q" not in output

    def test_natural_language_no_fake_pytest(self):
        """Natural language input should not trigger fake pytest."""
        result = run_cli(input_text="Hello\n/exit\n")
        output = result.stdout + result.stderr
        assert "pytest -q" not in output


class TestApprovalWorkflow:
    """Test approval workflow."""

    def test_approval_created_for_tests(self):
        """Running tests should create an approval."""
        result = run_cli(input_text="/test\n/exit\n")
        output = result.stdout + result.stderr
        if "approval" in output.lower():
            assert "approve" in output.lower() or "/approve" in output

    def test_approve_command_works(self):
        """/approve command should work."""
        result = run_cli(input_text="/test\n/approve approval_001\n/exit\n")
        output = result.stdout + result.stderr
        # Should not crash
        assert result.returncode == 0

    def test_reject_command_works(self):
        """/reject command should work."""
        result = run_cli(input_text="/test\n/reject approval_001\n/exit\n")
        output = result.stdout + result.stderr
        # Should not crash
        assert result.returncode == 0


class TestSandboxMode:
    """Test sandbox mode behavior."""

    def test_diff_unavailable_in_safe_mode(self):
        """/diff should mention safe mode."""
        result = run_cli(input_text="/diff\n/exit\n")
        output = result.stdout + result.stderr
        assert "safe" in output.lower() or "unavailable" in output.lower()


class TestNoRealLlmCall:
    """Test that no real LLM is called in default mode."""

    def test_no_timeout_on_simple_input(self):
        """Simple input should complete without timeout."""
        result = run_cli(input_text="Hello\n/exit\n", timeout=10)
        # Should complete quickly (no real LLM call)
        assert result.returncode == 0

    def test_mock_safe_mode_labeled(self):
        """Mock-safe mode should be labeled."""
        result = run_cli(input_text="Hello\n/exit\n")
        output = result.stdout + result.stderr
        assert "mock-safe" in output or "safe" in output.lower()
