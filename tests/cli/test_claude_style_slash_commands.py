"""Test Claude-style slash commands for Jarvis CLI."""

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


class TestSlashHelp:
    """Test /help command."""

    def test_help_does_not_create_task(self):
        """/help should not create a task."""
        result = run_cli(input_text="/help\n/exit\n")
        output = result.stdout + result.stderr
        assert "task.created" not in output
        assert "pytest -q" not in output

    def test_help_shows_available_commands(self):
        """/help should show available commands."""
        result = run_cli(input_text="/help\n/exit\n")
        output = result.stdout + result.stderr
        assert "/help" in output
        assert "/exit" in output


class TestSlashMode:
    """Test /mode command."""

    def test_mode_shows_current_mode(self):
        """/mode should show current mode."""
        result = run_cli(input_text="/mode\n/exit\n")
        output = result.stdout + result.stderr
        assert "safe" in output

    def test_mode_can_change_mode(self):
        """/mode should be able to change mode."""
        result = run_cli(input_text="/mode ask\n/mode\n/exit\n")
        output = result.stdout + result.stderr
        assert "ask" in output


class TestSlashPlan:
    """Test /plan command."""

    def test_plan_requires_input(self):
        """/plan should require input."""
        result = run_cli(input_text="/plan\n/exit\n")
        output = result.stdout + result.stderr
        assert "Plan requires input" in output or "Usage" in output

    def test_plan_outputs_plan(self):
        """/plan should output a plan without executing."""
        result = run_cli(input_text="/plan Inspect this repo\n/exit\n")
        output = result.stdout + result.stderr
        assert "Plan" in output


class TestSlashTest:
    """Test /test command."""

    def test_test_requires_approval(self):
        """/test should require approval or show dry-run."""
        result = run_cli(input_text="/test\n/exit\n")
        output = result.stdout + result.stderr
        # Should either show approval prompt or dry-run message
        assert "pytest" in output or "approval" in output.lower() or "dry" in output.lower()


class TestSlashPermissions:
    """Test /permissions command."""

    def test_permissions_shows_policy(self):
        """/permissions should show permission policy."""
        result = run_cli(input_text="/permissions\n/exit\n")
        output = result.stdout + result.stderr
        assert "safe" in output or "policy" in output.lower() or "mode" in output.lower()


class TestSlashApprovals:
    """Test /approvals command."""

    def test_approvals_shows_pending(self):
        """/approvals should show pending approvals."""
        result = run_cli(input_text="/approvals\n/exit\n")
        output = result.stdout + result.stderr
        assert "approval" in output.lower()
        assert "No pending" in output or "pending" in output.lower()


class TestSlashServer:
    """Test /server command."""

    def test_server_shows_status(self):
        """/server should show server status."""
        result = run_cli(input_text="/server\n/exit\n")
        output = result.stdout + result.stderr
        assert "Server" in output or "server" in output.lower()


class TestSlashWeb:
    """Test /web command."""

    def test_web_shows_url(self):
        """/web should show Web UI URL."""
        result = run_cli(input_text="/web\n/exit\n")
        output = result.stdout + result.stderr
        assert "Web UI" in output or "http" in output


class TestUnknownCommand:
    """Test unknown command handling."""

    def test_unknown_command_shows_suggestion(self):
        """Unknown command should show helpful suggestion."""
        result = run_cli(input_text="/nonexistent\n/exit\n")
        output = result.stdout + result.stderr
        assert "Unknown command" in output or "not found" in output.lower()

    def test_command_planned_not_active(self):
        """Command that is planned but not active should show message."""
        result = run_cli(input_text="/compact\n/exit\n")
        output = result.stdout + result.stderr
        assert "not active" in output.lower() or "planned" in output.lower()
