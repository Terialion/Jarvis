import os
import subprocess
import sys


def run_cli(*args, input_text=None, timeout=30):
    env = os.environ.copy()
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


def test_task_state_command_no_crash():
    result = run_cli("task", "state")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "State" in output or "No CLI coding state found." in output
    assert "Traceback" not in output


def test_slash_state_no_crash():
    result = run_cli(input_text="/state\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "State" in output or "No CLI coding state found." in output
    assert "Traceback" not in output
