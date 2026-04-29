"""Test Claude-style shell behavior for Jarvis CLI."""

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


class TestShellHeader:
    """Test shell header format."""

    def test_header_shows_jarvis_code(self):
        """Shell header should show 'Jarvis Code'."""
        result = run_cli(input_text="/exit\n")
        output = result.stdout + result.stderr
        assert "Jarvis Code" in output

    def test_header_shows_mode(self):
        """Shell header should show current mode."""
        result = run_cli(input_text="/exit\n")
        output = result.stdout + result.stderr
        assert "safe" in output

    def test_header_shows_help_hint(self):
        """Shell header should show help hint."""
        result = run_cli(input_text="/exit\n")
        output = result.stdout + result.stderr
        assert "/help" in output
        assert "/exit" in output


class TestShellCommands:
    """Test basic shell commands."""

    def test_exit_quits_shell(self):
        """/exit should quit the shell."""
        result = run_cli(input_text="/exit\n")
        assert result.returncode == 0

    def test_quit_quits_shell(self):
        """/quit should quit the shell."""
        result = run_cli(input_text="/quit\n")
        assert result.returncode == 0

    def test_clear_clears_context(self):
        """/clear should clear context without crash."""
        result = run_cli(input_text="/clear\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "Context cleared" in output or "cleared" in output.lower()

    def test_help_shows_commands(self):
        """/help should show available commands."""
        result = run_cli(input_text="/help\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "Commands:" in output or "commands" in output.lower()


class TestShellNoCrash:
    """Test that shell commands don't crash."""

    def test_status_no_crash(self):
        """/status should not crash."""
        result = run_cli(input_text="/status\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0

    def test_config_no_crash(self):
        """/config should not crash."""
        result = run_cli(input_text="/config\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0

    def test_doctor_no_crash(self):
        """/doctor should not crash."""
        result = run_cli(input_text="/doctor\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0

    def test_logs_no_crash(self):
        """/logs should not crash."""
        result = run_cli(input_text="/logs\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0


class TestShellOutput:
    """Test shell output format."""

    def test_tasks_shows_no_tasks(self):
        """/tasks should show 'No tasks' message when empty."""
        result = run_cli(input_text="/tasks\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "task" in output.lower()

    def test_approvals_shows_no_approvals(self):
        """/approvals should show 'No pending approvals' when empty."""
        result = run_cli(input_text="/approvals\n/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "approval" in output.lower()
