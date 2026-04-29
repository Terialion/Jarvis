"""Safety tests for Claude-style command mapping."""

import subprocess
import sys


def run_cli(*args, input_text=None, timeout=25):
    return subprocess.run(
        [sys.executable, "-m", "jarvis.cli", *args],
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        cwd="d:/jarvis",
    )


def test_test_command_does_not_silently_run_pytest():
    result = run_cli(input_text="/test\n/exit\n")
    out = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Approval required" in out or "dry-run" in out.lower()


def test_loop_command_no_scheduler_side_effect():
    result = run_cli(input_text="/loop\n/exit\n")
    out = result.stdout + result.stderr
    assert "status: unsupported" in out


def test_add_dir_requires_controlled_behavior():
    result = run_cli(input_text="/add-dir d:/tmp\n/exit\n")
    out = result.stdout + result.stderr
    assert "status: skeleton" in out


def test_setup_bedrock_does_not_print_secret():
    result = run_cli(input_text="/setup-bedrock\n/exit\n")
    out = result.stdout + result.stderr
    assert "status: unsupported" in out
    assert "sk-" not in out


def test_login_does_not_auto_open_browser():
    result = run_cli(input_text="/login\n/exit\n")
    out = result.stdout + result.stderr
    assert "status: unsupported" in out

