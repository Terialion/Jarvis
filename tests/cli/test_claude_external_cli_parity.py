"""Tests for Claude-style external CLI command behavior."""

import subprocess
import sys
import os


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


def test_positional_prompt_preserved():
    text = "晚上好"
    result = run_cli(text)
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert text in out
    assert "Investigate flaky tests" not in out


def test_print_prompt_preserved():
    text = "Inspect this repo. Do not modify files."
    result = run_cli("-p", text)
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert text in out
    assert "pytest -q" not in out


def test_resume_flags_controlled():
    latest = run_cli("-c")
    assert latest.returncode == 0
    assert "No previous session found." in (latest.stdout + latest.stderr)
    by_id = run_cli("-r", "not-found")
    assert by_id.returncode == 0
    assert "Session not found" in (by_id.stdout + by_id.stderr)
