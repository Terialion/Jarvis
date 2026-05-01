"""Tests for Claude-style external CLI command behavior."""

import os
import subprocess
import sys


def run_cli(*args, input_text=None, timeout=25):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONLEGACYWINDOWSSTDIO"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
        env=env,
    )


def test_bare_cli_starts_shell():
    result = run_cli(input_text="/exit\n")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Jarvis Code" in out


def test_help_flag_exits():
    result = run_cli("--help")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "usage" in out.lower()


def test_positional_prompt_routes_to_natural_response():
    result = run_cli("晚上好")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Task task_" not in out
    assert "Plan safe steps" not in out
    # "晚上好" is now correctly recognized as a greeting (not clarification)
    assert "你好" in out or "我需要再确认一下" in out
    assert "Investigate flaky tests" not in out


def test_print_prompt_repo_inspection_is_not_task_flow():
    result = run_cli("-p", "Inspect this repo. Do not modify files.")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    # Should NOT enter old task flow
    assert "Task task_" not in out
    assert "pytest -q" not in out
    # Now routed through AgentToolLoop (returns LLM fallback or work acknowledgement)
    assert "llm provider" in out.lower() or "无法连接" in out or "repository inspection" in out.lower()


def test_ask_prompt_oneshot_reuses_natural_path():
    result = run_cli("--ask", "Inspect this repo. Do not modify files.")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "LLM provider:" in out
    assert "Task task_" not in out
    assert "pytest -q" not in out
    assert "llm provider" in out.lower() or "repository inspection" in out.lower() or "work_type" in out.lower()


def test_resume_flags_controlled():
    latest = run_cli("-c")
    assert latest.returncode == 0
    assert "No previous session found." in (latest.stdout + latest.stderr)
    by_id = run_cli("-r", "not-found")
    assert by_id.returncode == 0
    assert "Session not found" in (by_id.stdout + by_id.stderr)
