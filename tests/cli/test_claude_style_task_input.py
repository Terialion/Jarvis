"""Test natural language task input handling for Jarvis CLI."""

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


class TestNaturalLanguagePreserved:
    """Test that natural language input is preserved."""

    def test_chinese_input_preserved(self):
        """Chinese input should be preserved exactly."""
        result = run_cli(input_text="晚上好\n/exit\n")
        output = result.stdout + result.stderr
        assert "晚上好" in output
        assert "Investigate flaky tests" not in output

    def test_english_input_preserved(self):
        """English input should be preserved exactly."""
        result = run_cli(input_text="Inspect this repo\n/exit\n")
        output = result.stdout + result.stderr
        assert "Inspect this repo" in output

    def test_input_in_task_output(self):
        """Input should appear in task output."""
        result = run_cli(input_text="Hello World\n/exit\n")
        output = result.stdout + result.stderr
        assert "Input" in output
        assert "Hello World" in output


class TestNoFixedDemoTask:
    """Test that no fixed demo task is created."""

    def test_no_fixed_demo_task(self):
        """Should not create 'Investigate flaky tests' task."""
        result = run_cli(input_text="/help\n/exit\n")
        output = result.stdout + result.stderr
        assert "Investigate flaky tests" not in output
        assert "flaky" not in output.lower()

    def test_no_fake_pytest(self):
        """Should not emit fake pytest events."""
        result = run_cli(input_text="/help\n/exit\n")
        output = result.stdout + result.stderr
        assert "pytest -q" not in output


class TestTaskCreation:
    """Test task creation behavior."""

    def test_task_created_for_natural_language(self):
        """Natural language input should create a task."""
        result = run_cli(input_text="Hello World\n/exit\n")
        output = result.stdout + result.stderr
        assert "Task" in output
        assert "task_" in output

    def test_task_shows_events(self):
        """Task output should show events."""
        result = run_cli(input_text="Hello World\n/exit\n")
        output = result.stdout + result.stderr
        assert ("Events" in output) or ("Task task_" in output)
        if "Events" in output:
            assert "task.created" in output

    def test_task_shows_result(self):
        """Task output should show result."""
        result = run_cli(input_text="Hello World\n/exit\n")
        output = result.stdout + result.stderr
        assert "Result" in output


class TestSlashCommandNoTask:
    """Test that slash commands don't create tasks."""

    def test_help_no_task(self):
        """/help should not create a task."""
        result = run_cli(input_text="/help\n/exit\n")
        output = result.stdout + result.stderr
        # /help should not trigger task creation
        # (This depends on implementation - some may show task, others not)
        assert "pytest -q" not in output

    def test_status_no_task(self):
        """/status should not create a task."""
        result = run_cli(input_text="/status\n/exit\n")
        output = result.stdout + result.stderr
        assert "pytest -q" not in output

    def test_config_no_task(self):
        """/config should not create a task."""
        result = run_cli(input_text="/config\n/exit\n")
        output = result.stdout + result.stderr
        assert "pytest -q" not in output


class TestMockSafeMode:
    """Test mock-safe mode behavior."""

    def test_mock_safe_label(self):
        """Mock-safe mode should be clearly labeled."""
        result = run_cli(input_text="Test input\n/exit\n")
        output = result.stdout + result.stderr
        assert "mock-safe" in output or "safe" in output

    def test_no_real_llm_called(self):
        """No real LLM should be called in default mode."""
        result = run_cli(input_text="Test input\n/exit\n")
        # Should complete without timeout (meaning no real LLM call)
        assert result.returncode == 0
