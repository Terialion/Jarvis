"""Tests for Claude-style CLI print mode behavior."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from jarvis import cli as cli_mod

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


def test_print_mode_greeting_is_natural():
    result = run_cli("-p", "hello")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "Task task_" not in output
    assert "Hi, I" in output or "Jarvis" in output


def test_print_mode_repo_inspection_not_task(monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_local_env_file", lambda *_a, **_k: None)
    monkeypatch.setattr(cli_mod, "_write_cli_diagnostic", lambda *_a, **_k: None)
    called: dict[str, str] = {}

    def _fake_runner(prompt: str, *, output_mode: str = "default") -> int:
        called["prompt"] = prompt
        called["output_mode"] = output_mode
        return 0

    monkeypatch.setattr(cli_mod, "_run_non_interactive_with_mode", _fake_runner)
    monkeypatch.setattr("sys.argv", ["python", "-p", "Inspect this repo. Do not modify files."])
    assert cli_mod.main() == 0
    assert called["prompt"] == "Inspect this repo. Do not modify files."
    assert called["output_mode"] == "default"
