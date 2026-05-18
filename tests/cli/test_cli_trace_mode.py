from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


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
        cwd=str(ROOT),
        env=env,
    )


def test_trace_off_by_default():
    result = run_cli(input_text="hello\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "skill.registry.loaded" not in output
    assert "Task task_" not in output


def test_trace_on_shows_internal_events():
    result = run_cli(input_text="/trace on\nhello\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Trace mode: on" in output or "trace on" in output.lower()
    assert "Task task_" not in output
    assert "Traceback" not in output


def test_trace_off_hides_internal_events_again():
    result = run_cli(input_text="/trace on\n/trace off\nhello\n/exit\n")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Trace mode: off" in output or "trace off" in output.lower()
    tail = output.rsplit("hello", 1)[-1]
    assert "skill.registry.loaded" not in tail
