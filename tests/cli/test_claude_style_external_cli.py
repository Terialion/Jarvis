"""Test external CLI commands for Jarvis CLI."""

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


def test_help_flag_exits_without_shell():
    result = run_cli("--help")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Commands" in output or "usage" in output.lower() or "Jarvis CLI" in output
    assert "Type /help" not in output


def test_bare_cli_starts_shell():
    result = run_cli(input_text="/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Jarvis Code" in output
    assert "/help" in output


def test_print_mode_repo_inspection_not_task():
    result = run_cli("-p", "Inspect this repo. Do not modify files.")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Task task_" not in output
    assert "pytest -q" not in output
    # Now routed through AgentToolLoop (returns LLM fallback or work acknowledgement)
    assert "jarvis" in output.lower() or "llm provider" in output.lower() or "无法连接" in output or "repository inspection" in output.lower()


def test_print_mode_greeting_not_task():
    result = run_cli("-p", "hello")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Task task_" not in output
    assert "I can" in output or "Hi, I’m here." in output or "Jarvis" in output


def test_task_run_uses_input():
    result = run_cli("task", "run", "Inspect this repo. Do not modify files.", "--safe")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Inspect this repo" in output
