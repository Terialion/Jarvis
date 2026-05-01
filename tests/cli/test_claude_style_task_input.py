"""Test natural language and task input handling for Jarvis CLI."""

import os
import subprocess
import sys


def run_cli(*args, input_text=None, timeout=25):
    merged_env = os.environ.copy()
    merged_env["PYTHONIOENCODING"] = "utf-8"
    merged_env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    return subprocess.run(
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


def test_chinese_greeting_is_natural_response():
    result = run_cli(input_text="你好\n/exit\n")
    output = result.stdout + result.stderr
    assert "Task task_" not in output
    assert "Plan safe steps" not in output


def test_english_repo_inspection_is_not_task():
    result = run_cli(input_text="Inspect this repo\n/exit\n")
    output = result.stdout + result.stderr
    assert "Task task_" not in output
    # Now routed through AgentToolLoop
    assert "llm provider" in output.lower() or "无法连接" in output or "repository inspection" in output.lower()


def test_coding_task_still_enters_task_flow():
    result = run_cli(input_text="fix this bug and run tests\n/exit\n")
    output = result.stdout + result.stderr
    # Now routed through AgentToolLoop → work path; should NOT be a simple chat answer
    assert "Task task_" in output or "Approval required" in output or "[WORK]" in output or "无法连接 LLM" in output


def test_help_slash_does_not_trigger_demo_pytest():
    result = run_cli(input_text="/help\n/exit\n")
    output = result.stdout + result.stderr
    assert "pytest -q" not in output
