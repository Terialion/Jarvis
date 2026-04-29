"""Test Claude-style external CLI commands for Jarvis CLI."""

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


class TestHelpFlag:
    """Test --help flag behavior."""

    def test_help_flag_exits_without_shell(self):
        """--help should show help and exit, not enter shell."""
        result = run_cli("--help")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "Commands" in output or "usage" in output.lower() or "Jarvis CLI" in output
        # Should not show shell prompt
        assert "Type /help" not in output

    def test_help_flag_shows_usage(self):
        """--help should show usage information."""
        result = run_cli("--help")
        output = result.stdout + result.stderr
        assert "python -m jarvis.cli" in output or "usage" in output.lower()


class TestBareCli:
    """Test bare CLI invocation."""

    def test_bare_cli_starts_shell(self):
        """Bare CLI should start interactive shell."""
        result = run_cli(input_text="/exit\n")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "Jarvis Code" in output
        assert "/help" in output

    def test_bare_cli_no_fixed_demo_task(self):
        """Bare CLI should not create fixed demo task."""
        result = run_cli(input_text="/exit\n")
        output = result.stdout + result.stderr
        assert "Investigate flaky tests" not in output
        assert "pytest -q" not in output


class TestExternalCommands:
    """Test external CLI commands."""

    def test_tools_prints_non_empty(self):
        """`python -m jarvis.cli tools` should print non-empty output."""
        result = run_cli("tools")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert output.strip()
        assert "tool" in output.lower() or "skill" in output.lower() or "capabilit" in output.lower()

    def test_config_shows_masked(self):
        """`python -m jarvis.cli config` should show masked config."""
        result = run_cli("config", "--show")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        # Should not leak secrets
        assert "sk-" not in output or "****" in output

    def test_server_status(self):
        """`python -m jarvis.cli server status` should run without crash."""
        result = run_cli("server", "status")
        # Should not crash (return code may be 0 or 1 depending on server status)
        assert result.returncode in (0, 1)
        assert "Server" in result.stdout + result.stderr

    def test_doctor_runs(self):
        """`python -m jarvis.cli doctor` should run diagnostics."""
        result = run_cli("doctor")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "Doctor" in output or "config" in output.lower()


class TestPrintMode:
    """Test -p (print) mode."""

    def test_print_mode_with_prompt(self):
        """`-p` mode should run non-interactively with prompt."""
        result = run_cli("-p", "Inspect this repo. Do not modify files.")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "Inspect this repo" in output
        assert "pytest -q" not in output

    def test_print_mode_preserves_input(self):
        """`-p` mode should preserve user input exactly."""
        result = run_cli("-p", "晚上好")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "晚上好" in output


class TestTaskRun:
    """Test task run command."""

    def test_task_run_uses_input(self):
        """`task run` should use actual input."""
        result = run_cli("task", "run", "Inspect this repo. Do not modify files.", "--safe")
        output = result.stdout + result.stderr
        assert result.returncode == 0
        assert "Inspect this repo" in output
        assert "pytest -q" not in output
