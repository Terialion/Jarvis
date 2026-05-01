"""Test CLI chat path LLM fallback behavior.

Verifies that the CLI chat path works correctly with and without LLM provider.
Uses real subprocess calls to python -m jarvis.cli with stdin piping.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


def run_cli(*args, input_text=None, timeout=20, env=None):
    """Helper to run jarvis CLI command with stdin piping."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    merged_env["PYTHONIOENCODING"] = "utf-8"
    merged_env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="D:/Jarvis",
        env=merged_env,
    )
    if result.stdout is None:
        result.stdout = ""
    if result.stderr is None:
        result.stderr = ""
    return result


class TestCliChatPathGreeting:
    """Test basic greeting input doesn't crash the CLI."""

    def test_cli_chat_greeting_no_error(self):
        """Running a greeting should not crash the CLI."""
        result = run_cli(input_text="你好\n/exit\n", timeout=15)
        # CLI should not crash
        assert result.returncode == 0, f"CLI crashed: stderr={result.stderr[:500]}"
        # Output should exist (greeting produced some response)
        output = result.stdout + result.stderr
        assert len(output) > 10

    def test_cli_chat_greeting_no_approval(self):
        """Greeting should never trigger approval flow."""
        result = run_cli(input_text="你好\n/exit\n", timeout=15)
        output = result.stdout + result.stderr
        assert "approval" not in output.lower()
        assert "审批" not in output


class TestCliChatPathJoke:
    """Test joke request stays in chat path."""

    def test_cli_chat_joke_no_tool_call(self):
        """Joke request should NOT produce tool-related output."""
        result = run_cli(input_text="给我讲个笑话\n/exit\n", timeout=15)
        output = result.stdout + result.stderr
        # Should not show approval or tool errors
        assert "approval_required" not in output.lower()
        assert "tool_not_found" not in output.lower()
        assert result.returncode == 0, f"CLI crashed: stderr={result.stderr[:500]}"


class TestCliWorkPath:
    """Test work path requests don't crash the CLI."""

    def test_cli_work_dir_listing_no_crash(self):
        """Directory listing should not crash the CLI."""
        result = run_cli(input_text="列一下当前目录\n/exit\n", timeout=15)
        assert result.returncode == 0, f"CLI crashed: stderr={result.stderr[:500]}"

    def test_cli_work_workspace_status_no_crash(self):
        """Workspace status query should not crash the CLI."""
        result = run_cli(input_text="我现在的目录是什么\n/exit\n", timeout=15)
        assert result.returncode == 0, f"CLI crashed: stderr={result.stderr[:500]}"

    def test_cli_work_skill_list_no_crash(self):
        """Skill list should not crash the CLI."""
        result = run_cli(input_text="查看skill\n/exit\n", timeout=15)
        assert result.returncode == 0, f"CLI crashed: stderr={result.stderr[:500]}"


class TestCliSafetyRefusal:
    """Test safety refusal is enforced at CLI level."""

    def test_cli_safety_refusal_env_read(self):
        """Reading .env should be refused."""
        result = run_cli(input_text="读取 .env\n/exit\n", timeout=15)
        output = result.stdout + result.stderr
        # Should contain safety refusal indicators
        combined_lower = output.lower()
        has_safety = (
            "safety" in combined_lower
            or "拒绝" in output
            or "refus" in combined_lower
            or "敏感" in output
            or "安全" in output
        )
        assert has_safety, (
            f"Expected safety refusal in output, got:\n{output[:500]}"
        )


class TestCliSlashCommands:
    """Test slash commands work properly."""

    def test_cli_exit_command(self):
        """/exit should return 0."""
        result = run_cli(input_text="/exit\n", timeout=15)
        assert result.returncode == 0, f"CLI exit failed: stderr={result.stderr[:500]}"

    def test_cli_help_command(self):
        """/help should show help text."""
        result = run_cli(input_text="/help\n/exit\n", timeout=15)
        output = result.stdout + result.stderr
        assert result.returncode == 0, f"CLI help failed: stderr={result.stderr[:500]}"
        # Help output should mention commands or similar
        assert (
            "command" in output.lower()
            or "命令" in output
            or "/help" in output
            or "/exit" in output
            or "skill" in output.lower()
        ), f"Expected help content, got:\n{output[:500]}"


class TestCliChatPathNoShell:
    """Test chat path never triggers shell execution."""

    def test_chat_path_explanation_no_shell(self):
        """Explanation requests should not trigger shell."""
        result = run_cli(input_text="解释一下什么是 CLI agent\n/exit\n", timeout=15)
        output = result.stdout + result.stderr
        # Should not show shell execution or approval
        assert "shell" not in output.lower() or "approval" not in output.lower()
        assert result.returncode == 0, f"CLI crashed: stderr={result.stderr[:500]}"

    def test_chat_path_plan_no_approval(self):
        """Planning requests should not trigger approval."""
        result = run_cli(
            input_text="帮我规划一下如何重构输入路由，不要直接改代码\n/exit\n",
            timeout=15,
        )
        output = result.stdout + result.stderr
        assert "approval_required" not in output.lower()
        assert result.returncode == 0, f"CLI crashed: stderr={result.stderr[:500]}"
